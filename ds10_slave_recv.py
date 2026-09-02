#!/usr/bin/env python3
"""DS10 从机接收监控脚本 (ticket 02 / 收发联调)。

在从机端 Jetson 上运行, 连从机 DS10 的串口 (默认 /dev/ttyUSB1)。
实现落地设计的混合定界法 (ticket 01):
  1. 静默间隔粗切: 串口空闲超过 --gap 秒, 认为一次突发结束;
  2. CRC 试探细切: 在缓冲区里从起点滑动, 要求首字节站号∈[1,247]、总长≥6,
     对递增候选长度试 CRC-16/MODBUS, 命中即切出一帧、前移起点继续 (解粘包);
  3. 尾部配不出 CRC 的字节保留到下次拼接 (解拆包)。
解出帧后读取数据区的 MARKER+seq 做丢帧/乱序/CRC 对账。

配套主机脚本: ds10_master_send.py (另一终端运行)。

用法:
  # 默认监听 /dev/ttyUSB1
  python3 ds10_slave_recv.py

  # 指定串口, 只接本机站号 1 的帧 (其余丢弃)
  python3 ds10_slave_recv.py -p /dev/ttyUSB1 --station 1

  # 精简输出 (只打印异常与周期统计)
  python3 ds10_slave_recv.py --quiet
"""

import argparse
import sys
import time

import serial

MARKER = b"\xF1\xF1"
MIN_FRAME = 6            # 站号+功能码+至少 2B 数据 + CRC2, 实际本协议帧更长
MAX_FRAME = 4200         # 缓冲区单帧上限保护 (略大于 DS10 4096 上限)


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 从机接收监控")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB1",
                    help="从机 DS10 串口 (默认 /dev/ttyUSB1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=0,
                    help="只接受该站号的帧, 0=不过滤全部接收 (默认 0)")
    ap.add_argument("--gap", type=float, default=0.02,
                    help="判定突发结束的空闲间隔秒数 (默认 0.02)")
    ap.add_argument("--quiet", action="store_true", help="只打印异常和周期统计")
    ap.add_argument("--stats-every", type=float, default=5.0,
                    help="周期统计打印间隔秒数 (默认 5)")
    ap.add_argument("--burst-detail", action="store_true",
                    help="超长实测: 打印每次 read 事件和每个静默突发的累计字节数, "
                         "用于判断超长帧是否跨突发(链路层分包)还是单突发到达(已重组)")
    return ap.parse_args()


class Stats:
    def __init__(self):
        self.frames = 0
        self.good = 0
        self.crc_err = 0
        self.filtered = 0
        self.recovered_bytes = 0   # CRC 试探丢弃的字节数
        self.last_seq = None
        self.lost = 0
        self.reorder = 0
        self.seen = set()
        self.bytes = 0
        self.t0 = time.monotonic()


def try_extract_frames(buf, stats, station_filter, quiet):
    """从 buf 里用 CRC 试探切出尽可能多的完整帧, 返回剩余未消费字节。

    buf: bytearray (原地消费); 命中一帧就打印/对账。
    """
    out = bytearray(buf)
    pos = 0
    n = len(out)
    while pos < n:
        # 首字节站号合法性过滤: 非 1-247 直接滑过一个字节 (重新同步)
        if not (1 <= out[pos] <= 247):
            pos += 1
            stats.recovered_bytes += 1
            continue
        # 从 pos 起试递增候选帧长, 命中 CRC 即认定一帧
        hit = None
        max_try = min(n - pos, MAX_FRAME)
        for flen in range(MIN_FRAME, max_try + 1):
            frame = bytes(out[pos:pos + flen])
            if modbus_crc16(frame[:-2]) == frame[-2:]:
                hit = (flen, frame)
                break
        if hit is None:
            # pos 处配不出任何完整帧: 可能是半帧(等更多字节) 或 噪声
            break
        flen, frame = hit
        _handle_frame(frame, stats, station_filter, quiet)
        pos += flen
    # 消费掉 [0, pos), 保留尾部
    return out[pos:]


def _handle_frame(frame, stats, station_filter, quiet):
    stats.frames += 1
    stats.bytes += len(frame)
    station, func = frame[0], frame[1]
    # 数据区: 跳过 Modbus 0x10 头 (站号1+功能1+addr2+qty2+bytecount1 = 7B)
    seq = None
    data_region = frame[7:-2] if len(frame) >= 9 else b""
    if data_region[:2] == MARKER and len(data_region) >= 4:
        seq = (data_region[2] << 8) | data_region[3]

    if station_filter and station != station_filter:
        stats.filtered += 1
        return

    stats.good += 1
    # 对账
    tag = ""
    if seq is not None:
        if seq in stats.seen:
            stats.reorder += 1
            tag = " [重复/乱序]"
        stats.seen.add(seq)
        if stats.last_seq is not None and seq > stats.last_seq + 1:
            gap = seq - stats.last_seq - 1
            stats.lost += gap
            tag = f" [丢帧 {gap} 个: seq {stats.last_seq+1}..{seq-1}]"
        if stats.last_seq is None or seq > stats.last_seq:
            stats.last_seq = seq

    if not quiet or tag:
        ts = time.strftime("%H:%M:%S")
        seqs = f"seq={seq}" if seq is not None else "seq=?"
        print(f"[{ts}] 站号={station} 功能=0x{func:02X} 帧长={len(frame)}B "
              f"{seqs} CRC正确{tag}")


def print_stats(stats):
    dur = time.monotonic() - stats.t0
    rate = stats.bytes / dur if dur > 0 else 0
    print("-" * 68)
    print(f"[统计 +{dur:5.0f}s] 收帧 {stats.frames} (有效 {stats.good} "
          f"过滤 {stats.filtered}) | 丢帧 {stats.lost} 重复 {stats.reorder} "
          f"| 重同步丢字节 {stats.recovered_bytes} | {rate:.0f}B/s")
    print("-" * 68)


def main():
    args = parse_args()
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备存在 (ls /dev/ttyUSB*)、权限 (dialout 组)、未被占用。",
              file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1")
    print(f"混合定界 (静默 {args.gap*1000:g}ms 粗切 + CRC 试探细切) | "
          f"{'接受全部站号' if args.station == 0 else '仅站号 '+str(args.station)}")
    print("Ctrl-C 停止")
    print("-" * 68)

    buf = bytearray()
    last_rx = None
    stats = Stats()
    next_stats = time.monotonic() + args.stats_every
    burst_bytes = 0        # 当前静默突发累计字节
    burst_reads = 0        # 当前突发内 read 次数
    burst_no = 0
    try:
        while True:
            n = ser.in_waiting
            now = time.monotonic()
            if n:
                chunk = ser.read(n)
                buf += chunk
                last_rx = now
                if args.burst_detail:
                    burst_bytes += len(chunk)
                    burst_reads += 1
                    print(f"    read #{burst_reads} +{len(chunk)}B "
                          f"(突发累计 {burst_bytes}B)")
                # 突发进行中也尝试切帧 (粘包时能及时消费)
                buf = try_extract_frames(buf, stats, args.station, args.quiet)
            elif buf and last_rx is not None and (now - last_rx) >= args.gap:
                # 突发结束: 再切一次, 仍有残留说明是半帧噪声, 丢弃并重同步
                buf = try_extract_frames(buf, stats, args.station, args.quiet)
                if buf:
                    stats.recovered_bytes += len(buf)
                    if not args.quiet:
                        print(f"    (突发结束丢弃 {len(buf)}B 无法配对字节, 重同步)")
                    buf.clear()
                if args.burst_detail and burst_bytes:
                    burst_no += 1
                    print(f"[突发#{burst_no} 结束] 共 {burst_bytes}B / "
                          f"{burst_reads} 次 read")
                burst_bytes = 0
                burst_reads = 0
                last_rx = None
            else:
                time.sleep(0.002)
            if now >= next_stats:
                print_stats(stats)
                next_stats = now + args.stats_every
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print("\n" + "=" * 68)
        print_stats(stats)
        seen_n = len(stats.seen)
        if seen_n:
            lo, hi = min(stats.seen), max(stats.seen)
            expected = hi - lo + 1
            print(f"seq 覆盖 {lo}..{hi} (期望 {expected} 帧, 实收 {seen_n} 帧, "
                  f"丢 {expected - seen_n} 帧, 到达率 {seen_n/expected*100:.1f}%)")
        print("串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
