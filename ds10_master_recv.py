#!/usr/bin/env python3
"""DS10 主机接收监控脚本 (上行方向 / 收发联调)。

在主机端 Jetson 上运行, 连主机 DS10 的串口 (默认 /dev/ttyUSB0)。
主机在 Modbus 模式下接收来自多台从机的上报帧, 用帧首字节的站号识别来源。
实现与下行一致的混合定界法 (ticket 01):
  1. 静默间隔粗切: 串口空闲超过 --gap 秒, 认为一次突发结束;
  2. CRC 试探细切: 从起点滑动, 首字节站号∈[1,247]、总长≥6, 试 CRC-16/MODBUS,
     命中即切帧、前移起点继续 (解粘包);
  3. 尾部配不出 CRC 的字节保留到下次拼接 (解拆包)。
按站号分别对账 (丢帧/乱序/到达率), 这是"1 主 15 从"里区分来源的核心。

配套从机脚本: ds10_slave_send.py (另一终端运行)。

用法:
  # 默认监听 /dev/ttyUSB0, 接受全部站号
  python3 ds10_master_recv.py

  # 只关注站号 1、3、5 的从机
  python3 ds10_master_recv.py -p /dev/ttyUSB0 --stations 1,3,5

  # 精简输出 (只打印异常与周期统计)
  python3 ds10_master_recv.py --quiet
"""

import argparse
import sys
import time

import serial

MARKER = b"\xF1\xF1"
MIN_FRAME = 6
MAX_FRAME = 4200


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 主机接收监控 (上行)")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0",
                    help="主机 DS10 串口 (默认 /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--stations", default="",
                    help="逗号分隔的关注站号白名单, 空=接受全部 (默认空)")
    ap.add_argument("--gap", type=float, default=0.02,
                    help="判定突发结束的空闲间隔秒数 (默认 0.02)")
    ap.add_argument("--quiet", action="store_true", help="只打印异常和周期统计")
    ap.add_argument("--stats-every", type=float, default=5.0,
                    help="周期统计打印间隔秒数 (默认 5)")
    ap.add_argument("--burst-detail", action="store_true",
                    help="超长实测: 打印每次 read 事件和每个静默突发的累计字节数, "
                         "用于判断超长帧是否跨突发(链路层分包)还是单突发到达(已重组)")
    return ap.parse_args()


class StationStat:
    """单个从机站号的接收统计。"""
    def __init__(self):
        self.frames = 0
        self.last_seq = None
        self.lost = 0
        self.reorder = 0
        self.seen = set()
        self.bytes = 0


class Stats:
    def __init__(self):
        self.by_station = {}      # station -> StationStat
        self.filtered = 0
        self.recovered_bytes = 0
        self.t0 = time.monotonic()

    def station(self, sid):
        if sid not in self.by_station:
            self.by_station[sid] = StationStat()
        return self.by_station[sid]


def try_extract_frames(buf, stats, whitelist, quiet):
    """从 buf 用 CRC 试探切出完整帧, 返回剩余未消费字节。"""
    out = bytearray(buf)
    pos = 0
    n = len(out)
    while pos < n:
        if not (1 <= out[pos] <= 247):
            pos += 1
            stats.recovered_bytes += 1
            continue
        hit = None
        max_try = min(n - pos, MAX_FRAME)
        for flen in range(MIN_FRAME, max_try + 1):
            frame = bytes(out[pos:pos + flen])
            if modbus_crc16(frame[:-2]) == frame[-2:]:
                hit = (flen, frame)
                break
        if hit is None:
            break
        flen, frame = hit
        _handle_frame(frame, stats, whitelist, quiet)
        pos += flen
    return out[pos:]


def _handle_frame(frame, stats, whitelist, quiet):
    station, func = frame[0], frame[1]
    seq = None
    data_region = frame[7:-2] if len(frame) >= 9 else b""
    if data_region[:2] == MARKER and len(data_region) >= 4:
        seq = (data_region[2] << 8) | data_region[3]

    if whitelist and station not in whitelist:
        stats.filtered += 1
        return

    st = stats.station(station)
    st.frames += 1
    st.bytes += len(frame)

    tag = ""
    if seq is not None:
        if seq in st.seen:
            st.reorder += 1
            tag = " [重复/乱序]"
        st.seen.add(seq)
        if st.last_seq is not None and seq > st.last_seq + 1:
            gap = seq - st.last_seq - 1
            st.lost += gap
            tag = f" [丢帧 {gap} 个: seq {st.last_seq+1}..{seq-1}]"
        if st.last_seq is None or seq > st.last_seq:
            st.last_seq = seq

    if not quiet or tag:
        ts = time.strftime("%H:%M:%S")
        seqs = f"seq={seq}" if seq is not None else "seq=?"
        print(f"[{ts}] 来源站号={station:<3} 功能=0x{func:02X} 帧长={len(frame)}B "
              f"{seqs} CRC正确{tag}")


def print_stats(stats):
    dur = time.monotonic() - stats.t0
    print("-" * 68)
    print(f"[统计 +{dur:5.0f}s] 活跃从机 {len(stats.by_station)} 台 | "
          f"过滤 {stats.filtered} | 重同步丢字节 {stats.recovered_bytes}")
    for sid in sorted(stats.by_station):
        st = stats.by_station[sid]
        rate = st.bytes / dur if dur > 0 else 0
        seen_n = len(st.seen)
        cover = ""
        if seen_n:
            lo, hi = min(st.seen), max(st.seen)
            exp = hi - lo + 1
            cover = f" 到达率 {seen_n/exp*100:.1f}% (seq {lo}..{hi})"
        print(f"  站号 {sid:<3}: 收帧 {st.frames:<5} 丢帧 {st.lost:<4} "
              f"重复 {st.reorder:<3} {rate:6.0f}B/s{cover}")
    print("-" * 68)


def main():
    args = parse_args()
    whitelist = {int(x) for x in args.stations.split(",") if x.strip()}
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备存在 (ls /dev/ttyUSB*)、权限 (dialout 组)、未被占用。",
              file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1")
    print(f"混合定界 (静默 {args.gap*1000:g}ms 粗切 + CRC 试探细切) | "
          f"{'接受全部站号' if not whitelist else '仅站号 '+str(sorted(whitelist))}")
    print("Ctrl-C 停止")
    print("-" * 68)

    buf = bytearray()
    last_rx = None
    stats = Stats()
    next_stats = time.monotonic() + args.stats_every
    burst_bytes = 0
    burst_reads = 0
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
                buf = try_extract_frames(buf, stats, whitelist, args.quiet)
            elif buf and last_rx is not None and (now - last_rx) >= args.gap:
                buf = try_extract_frames(buf, stats, whitelist, args.quiet)
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
        print("串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
