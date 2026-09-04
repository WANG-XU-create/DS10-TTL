#!/usr/bin/env python3
"""DS10 主机发送监控脚本 (ticket 02 / 收发联调)。

在主机端 Jetson 上运行, 连主机 DS10 的串口 (默认 /dev/ttyUSB0)。
按落地协议组标准 Modbus RTU 帧, 向指定站号的从机连续发送随机数据:
  帧 = [站号][0x10][起始地址 2B][寄存器数 2B][字节数 1B][MARKER+seq+随机数据][CRC16]
其中 MARKER(0xF1F1)+seq(2B) 嵌在数据区开头, 供从机接收脚本做丢帧对账。

配套从机脚本: ds10_slave_recv.py (另一终端运行)。

用法:
  # 默认: 向站号 1 连续发送, 载荷 32/128/240 轮换, 间隔 0.5s
  python3 ds10_master_send.py

  # 指定串口/站号/节奏
  python3 ds10_master_send.py -p /dev/ttyUSB0 --station 1 --interval 0.2

  # 固定载荷大小、发 200 帧后停止
  python3 ds10_master_send.py --sizes 128 --count 200
"""

import argparse
import os
import sys
import time

import serial

MARKER = b"\xF1\xF1"     # 数据区起始标记, 与从机脚本约定一致


def modbus_crc16(data):
    """标准 Modbus RTU CRC16 (多项式 0xA001), 低字节在前 2 字节。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_frame(station, seq, payload):
    """构造合法 Modbus 0x10 帧, 把 MARKER+seq 放在数据区开头。

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
    ap = argparse.ArgumentParser(description="DS10 主机发送监控")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0",
                    help="主机 DS10 串口 (默认 /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1, help="目标从机站号 1-247 (默认 1)")
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

    oversize_plan = None
    if args.oversize:
        # 超长分包实测: 固定载荷, 每个发 1 帧 (seq 递增, 便于接收端逐帧对照长度)
        oversize_plan = [1400, 1500, 2000, 4096]

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备存在 (ls /dev/ttyUSB*)、权限 (dialout 组)、未被占用。",
              file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1")
    if oversize_plan:
        print(f"超长分包实测 | 向站号 {args.station} 依次发送载荷 {oversize_plan}B "
              f"各 1 帧 | 间隔 {args.interval}s")
    else:
        print(f"向站号 {args.station} 发送 | 载荷 {sizes} 轮换 | 间隔 {args.interval}s | "
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
            print(f"[发送 seq={seq:<5}] 站号={args.station} 载荷={size:>4}B "
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
        print(f"最后 seq={seq-1}。从机端可用此对账丢帧。串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
