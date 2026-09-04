#!/usr/bin/env python3
"""DS10 端到端延迟测试 — 主机探针端 (RTT 测量)。

在主机端 Jetson 上运行, 连主机 DS10 串口 (默认 /dev/ttyUSB0)。
向从机发探针帧并记录发送时刻 t0, 等从机回声帧返回记录 t1, RTT = t1 - t0,
单向延迟 ≈ RTT / 2。全程只用主机一个时钟, 不依赖两机时钟同步 (最准)。
每帧数据区嵌入唯一探针 id, 用于把回帧与发帧精确配对、避免错配。

配套从机脚本: ds10_latency_echo.py (先在从机端启动)。

用法:
  # 默认: 站号1, 尺寸 32/240/1400B 各测 50 次, 每次超时 1s
  python3 ds10_latency_probe.py -p /dev/ttyUSB0 --station 1

  # 自定义
  python3 ds10_latency_probe.py --sizes 32,240,1400 --rounds 100 --timeout 1.0
"""

import argparse
import os
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


def build_text_payload(size, probe_id):
    """生成可读文本载荷 (probe_id 4B + 循环文本填充)。"""
    TEXT = b"DS10Test_"
    pid = probe_id.to_bytes(4, "big")
    remaining = max(0, size - len(pid))
    text_part = (TEXT * (remaining // len(TEXT) + 1))[:remaining]
    return pid + text_part


def build_probe(station, probe_id, size):
    """探针帧: 数据区 = MARKER + probe_id(4B) + 填充到 size 字节。"""
    payload = build_text_payload(size, probe_id)
    data = MARKER + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def probe_id_of(frame):
    """从回帧里取出 probe_id, 取不出返回 None。"""
    data_region = frame[7:-2] if len(frame) >= 9 else b""
    if data_region[:2] == MARKER and len(data_region) >= 6:
        return int.from_bytes(data_region[2:6], "big")
    return None


def extract_frames(buf):
    out = bytearray(buf)
    frames = []
    pos = 0
    n = len(out)
    while pos < n:
        if not (1 <= out[pos] <= 247):
            pos += 1
            continue
        hit = None
        max_try = min(n - pos, MAX_FRAME)
        for flen in range(MIN_FRAME, max_try + 1):
            fr = bytes(out[pos:pos + flen])
            if modbus_crc16(fr[:-2]) == fr[-2:]:
                hit = (flen, fr)
                break
        if hit is None:
            break
        flen, fr = hit
        frames.append(fr)
        pos += flen
    return frames, out[pos:]


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 延迟测试 - 主机探针端")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0",
                    help="主机 DS10 串口 (默认 /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1, help="目标从机站号 (默认 1)")
    ap.add_argument("--sizes", default="32,240,1400",
                    help="逗号分隔的探针帧载荷字节数 (默认 32,240,1400)")
    ap.add_argument("--rounds", type=int, default=50, help="每种尺寸测量次数 (默认 50)")
    ap.add_argument("--timeout", type=float, default=3.0,
                    help="单次等待回帧超时秒数, 大帧往返慢需放宽 (默认 3.0)")
    ap.add_argument("--interval", type=float, default=0.1,
                    help="两次探针之间的间隔秒数, 让链路静默 (默认 0.1)")
    return ap.parse_args()


def serial_ms(frame_bytes, baud):
    """单程串口传输时间(ms): 8N1 每字节 10 bit。"""
    return frame_bytes * 10.0 / baud * 1000.0


def measure_one(ser, station, probe_id, size, timeout):
    """发一帧探针, 等匹配 probe_id 的回帧, 返回 RTT 秒; 超时/错配返回 None。"""
    ser.reset_input_buffer()
    frame = build_probe(station, probe_id, size)
    t0 = time.monotonic()
    ser.write(frame)
    ser.flush()

    buf = bytearray()
    deadline = t0 + timeout
    while time.monotonic() < deadline:
        n = ser.in_waiting
        if n:
            buf += ser.read(n)
            frames, buf = extract_frames(buf)
            for fr in frames:
                if probe_id_of(fr) == probe_id:
                    return time.monotonic() - t0
        else:
            time.sleep(0.0005)
    return None


def summarize(name, rtts, frame_len, baud):
    """打印一组 RTT 统计, 并扣除 4 段串口传输时间得到纯链路 RTT。

    RTT 含 4 段串口传输: 主机 TX + 从机 RX + 从机 TX + 主机 RX。
    纯链路 RTT = RTT - 4×单程串口传输, 反映无线 + DS10 内部处理开销。
    """
    if not rtts:
        print(f"  {name}: 无有效样本 (全部超时/丢失)")
        return
    ms = sorted(r * 1000 for r in rtts)
    n = len(ms)
    mean = sum(ms) / n
    p50 = ms[n // 2]
    p95 = ms[min(n - 1, int(n * 0.95))]
    serial_4 = 4.0 * serial_ms(frame_len, baud)   # 往返 4 段串口传输
    link_mean = max(0.0, mean - serial_4)
    link_p50 = max(0.0, p50 - serial_4)
    print(f"  {name} (整帧 {frame_len}B):")
    print(f"    原始 RTT : 均 {mean:7.2f}ms  中位 {p50:7.2f}ms  p95 {p95:7.2f}ms  "
          f"最小 {ms[0]:7.2f}ms  最大 {ms[-1]:7.2f}ms")
    print(f"    串口传输 : 4 段共 {serial_4:6.2f}ms (单程 {serial_ms(frame_len, baud):.2f}ms×4)")
    print(f"    纯链路RTT: 均 {link_mean:7.2f}ms  中位 {link_p50:7.2f}ms  "
          f"-> 单向无线 ≈ {link_mean/2:.2f}ms")


def main():
    args = parse_args()
    sizes = [max(6, int(x)) for x in args.sizes.split(",") if x.strip()]
    if not sizes:
        print("sizes 不能为空", file=sys.stderr)
        return 1
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1 | 目标站号 {args.station}")
    print(f"尺寸 {sizes} 各测 {args.rounds} 次 | 超时 {args.timeout}s")
    print("请确认从机端 ds10_latency_echo.py 已启动。Ctrl-C 停止。")
    print("-" * 68)

    probe_id = 0
    results = {}
    lost = {}
    frame_lens = {}
    try:
        for size in sizes:
            rtts = []
            miss = 0
            for _ in range(args.rounds):
                probe_id += 1
                # record the actual on-wire frame length for serial-time subtraction
                frame_lens[size] = len(build_probe(args.station, probe_id, size))
                rtt = measure_one(ser, args.station, probe_id, size, args.timeout)
                if rtt is None:
                    miss += 1
                else:
                    rtts.append(rtt)
                if args.interval > 0:
                    time.sleep(args.interval)
            results[size] = rtts
            lost[size] = miss
            done = len(rtts)
            print(f"[{size:>4}B] 完成 {done}/{args.rounds} (丢失 {miss})")
    except KeyboardInterrupt:
        print("\n中断。")
    finally:
        ser.close()

    print("\n" + "=" * 68)
    print("端到端往返延迟统计 (RTT = 主机发→从机回声→主机收)")
    print("-" * 68)
    for size in sizes:
        summarize(f"{size:>4}B", results.get(size, []), frame_lens.get(size, size), args.baud)
        if lost.get(size):
            print(f"    (丢失/超时 {lost[size]} 次)")
    print("\n注: 纯链路RTT 已扣除 4 段串口传输(主机TX+从机RX+从机TX+主机RX),")
    print("    反映 DS10 双向无线 + 从机回声处理; 单向无线 ≈ 纯链路RTT/2 (略偏大)。")
    print("串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
