#!/usr/bin/env python3
"""DS10 文件发送端 —— 读文本/二进制文件，分帧透传。

用法:
  python3 ds10_send_file.py --port /dev/ttyUSB0 --file test.txt --station 1 --chunk 200

接收端用 ds10_recv_file.py，重组后 diff 验证完整性。
"""

import argparse
import os
import sys
import time

import serial

MARKER = b"\xF1\xF1"


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_frame(station, seq, payload, is_last):
    """标准 Modbus 0x10 帧。MARKER + seq(2B) + is_last(1B) + payload_len(2B) + payload。"""
    flag = 1 if is_last else 0
    payload_len = len(payload)
    data = MARKER + bytes(((seq >> 8) & 0xFF, seq & 0xFF, flag,
                           (payload_len >> 8) & 0xFF, payload_len & 0xFF)) + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def main():
    ap = argparse.ArgumentParser(description="DS10 文件发送端")
    ap.add_argument("--port", required=True, help="串口设备 (如 /dev/ttyUSB0)")
    ap.add_argument("--file", required=True, help="要发送的文件")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1, help="目标站号 (默认 1)")
    ap.add_argument("--chunk", type=int, default=200, help="每帧载荷字节数 (默认 200)")
    ap.add_argument("--interval", type=float, default=0.1, help="帧间间隔秒 (默认 0.1)")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"文件不存在: {args.file}", file=sys.stderr)
        return 1

    with open(args.file, "rb") as f:
        content = f.read()

    if not content:
        print(f"文件为空: {args.file}", file=sys.stderr)
        return 1

    total_bytes = len(content)
    chunks = []
    offset = 0
    while offset < total_bytes:
        end = min(offset + args.chunk, total_bytes)
        chunks.append(content[offset:end])
        offset = end

    print(f"文件: {args.file}  大小: {total_bytes} B  分成 {len(chunks)} 帧 (每帧 ≤{args.chunk}B)")
    print(f"站号: {args.station}  串口: {args.port} @ {args.baud} 8N1  间隔: {args.interval*1000:.0f}ms")
    print("=" * 68)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        return 1

    start_time = time.time()
    for seq, chunk in enumerate(chunks):
        is_last = (seq == len(chunks) - 1)
        frame = build_frame(args.station, seq, chunk, is_last)
        t0 = time.monotonic()
        ser.write(frame)
        ser.flush()
        dt = time.monotonic() - t0
        print(f"[{seq+1}/{len(chunks)}]  seq={seq}  chunk={len(chunk)}B  "
              f"write={dt*1000:.1f}ms  {'[最后一帧]' if is_last else ''}")
        if not is_last:
            time.sleep(args.interval)

    elapsed = time.time() - start_time
    ser.close()
    print("=" * 68)
    print(f"发送完成。总耗时: {elapsed:.2f}s  平均速率: {total_bytes/elapsed:.0f} B/s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
