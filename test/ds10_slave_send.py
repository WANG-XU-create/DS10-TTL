#!/usr/bin/env python3
"""DS10 从机发送监控脚本 (上行方向 / 收发联调)。

在从机端 Jetson 上运行, 连从机 DS10 的串口 (默认 /dev/ttyUSB1)。
从机把自己的站号填进帧首字节, 主机在 Modbus 模式下据此识别数据来源。
帧格式与下行脚本一致 (标准 Modbus 0x10 帧 + MARKER+seq 嵌在数据区):
  帧 = [本机站号][0x10][起始 2B][寄存器数 2B][字节数 1B][MARKER+seq+随机数据][CRC16]

配套主机脚本: ds10_master_recv.py (另一终端运行)。

用法:
  # 默认: 本机站号 1, 从 /dev/ttyUSB1 发送, 载荷 32/128/240 轮换, 间隔 0.5s
  python3 ds10_slave_send.py

  # 指定串口/本机站号/节奏
  python3 ds10_slave_send.py -p /dev/ttyUSB1 --station 3 --interval 0.2

  # 固定载荷、发 200 帧后停止
  python3 ds10_slave_send.py --sizes 128 --count 200
"""

import argparse
import os
import sys
import time

import serial

MARKER = b"\xF1\xF1"     # 数据区起始标记, 与主机接收脚本约定一致


def modbus_crc16(data):
    """标准 Modbus RTU CRC16 (多项式 0xA001), 低字节在前 2 字节。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_frame(station, seq, payload):
    """构造合法 Modbus 0x10 帧, 首字节为本机站号, MARKER+seq 放数据区开头。

    注: 字节数字段掩码为 & 0xFF —— DS10 不解析该字段、CRC 试探定界也不依赖它,
    这样超长载荷 (>255B 数据区) 不会撑爆单字节, 帧头 7 字节布局保持不变。
    """
    data = MARKER + bytes(((seq >> 8) & 0xFF, seq & 0xFF)) + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 从机发送监控 (上行)")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB1",
                    help="从机 DS10 串口 (默认 /dev/ttyUSB1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1,
                    help="本机站号 1-247, 主机据此识别来源 (默认 1)")
    ap.add_argument("--sizes", default="32,128,240",
                    help="逗号分隔的载荷字节数, 逐帧轮换 (默认 32,128,240)")
    ap.add_argument("--interval", type=float, default=0.5, help="帧间隔秒数 (默认 0.5)")
    ap.add_argument("--count", type=int, default=0, help="发送帧数, 0=无限 (默认 0)")
    ap.add_argument("--oversize", action="store_true",
                    help="超长分包实测模式: 忽略 sizes/count, 固定发 1400/1500/2000/4096B 各 1 帧")
    return ap.parse_args()


def main():
    args = parse_args()
    if not 1 <= args.station <= 247:
        print(f"station 必须 1-247, 当前 {args.station}", file=sys.stderr)
        return 1
    sizes = [max(0, int(x)) for x in args.sizes.split(",") if x.strip()]
    if not sizes:
        print("sizes 不能为空", file=sys.stderr)
        return 1

    oversize_plan = [1400, 1500, 2000, 4096] if args.oversize else None

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备存在 (ls /dev/ttyUSB*)、权限 (dialout 组)、未被占用。",
              file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1")
    if oversize_plan:
        print(f"超长分包实测 | 本机站号 {args.station} 依次上报载荷 {oversize_plan}B "
              f"各 1 帧 | 间隔 {args.interval}s")
    else:
        print(f"本机站号 {args.station} 上报 | 载荷 {sizes} 轮换 | 间隔 {args.interval}s | "
              f"{'无限' if args.count == 0 else str(args.count)+' 帧'}")
    print("Ctrl-C 停止")
    print("-" * 68)

    seq = 0
    sent_bytes = 0
    t_start = time.monotonic()
    try:
        while True:
            if oversize_plan:
                if seq >= len(oversize_plan):
                    break
                size = oversize_plan[seq]
            else:
                if args.count and seq >= args.count:
                    break
                size = sizes[seq % len(sizes)]
            payload = os.urandom(size)
            frame = build_frame(args.station, seq, payload)
            ser.write(frame)
            ser.flush()
            sent_bytes += len(frame)
            elapsed = time.monotonic() - t_start
            rate = sent_bytes / elapsed if elapsed > 0 else 0
            print(f"[发送 seq={seq:<5}] 本机站号={args.station} 载荷={size:>4}B "
                  f"整帧={len(frame):>5}B  累计 {sent_bytes/1024:7.1f}KB "
                  f"均速 {rate:6.0f}B/s")
            seq += 1
            if args.interval > 0:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        dur = time.monotonic() - t_start
        print("\n" + "=" * 68)
        print(f"共发送 {seq} 帧 / {sent_bytes/1024:.2f} KB, 耗时 {dur:.1f}s")
        print(f"最后 seq={seq-1}。主机端可用此对账丢帧。串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
