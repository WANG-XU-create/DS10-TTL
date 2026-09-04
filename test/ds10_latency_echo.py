#!/usr/bin/env python3
"""DS10 端到端延迟测试 — 从机回声端 (echo responder)。

在从机端 Jetson 上运行, 连从机 DS10 串口 (默认 /dev/ttyUSB1)。
收到主机发来的探针帧后, 立即原样回发出去 (回声), 供主机端计算往返时间 RTT。
用混合定界法切帧, 保证回发的是完整帧而非字节流碎片。

配套主机脚本: ds10_latency_probe.py (另一终端/另一台机运行)。

用法:
  python3 ds10_latency_echo.py -p /dev/ttyUSB1 --station 1
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
    ap = argparse.ArgumentParser(description="DS10 延迟测试 - 从机回声端")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB1",
                    help="从机 DS10 串口 (默认 /dev/ttyUSB1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1,
                    help="只回声该站号的帧, 回发时保持原站号不变 (默认 1)")
    ap.add_argument("--gap", type=float, default=0.02,
                    help="判定突发结束的空闲间隔秒数 (默认 0.02)")
    return ap.parse_args()


def extract_frames(buf, station):
    """从 buf 用 CRC 试探切出完整帧, 返回 (整帧字节列表, 剩余字节)。"""
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


def main():
    args = parse_args()
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1 | 回声站号 {args.station}")
    print("等待主机探针帧, 收到即原样回发。Ctrl-C 停止。")
    print("-" * 60)

    buf = bytearray()
    last_rx = None
    echoed = 0
    try:
        while True:
            n = ser.in_waiting
            now = time.monotonic()
            if n:
                buf += ser.read(n)
                last_rx = now
                frames, buf = extract_frames(buf, args.station)
                for fr in frames:
                    # 只回声目标站号的帧, 原样回发 (保持站号/功能码/CRC 不变)
                    if fr[0] == args.station:
                        ser.write(fr)
                        ser.flush()
                        echoed += 1
                        if echoed % 50 == 0:
                            print(f"已回声 {echoed} 帧")
            elif buf and last_rx is not None and (now - last_rx) >= args.gap:
                _, buf = extract_frames(buf, args.station)
                buf.clear()
                last_rx = None
            else:
                time.sleep(0.001)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print(f"\n共回声 {echoed} 帧。串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
