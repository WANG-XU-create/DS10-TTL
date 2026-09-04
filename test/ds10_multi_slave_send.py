#!/usr/bin/env python3
"""DS10 双(多)从机并发发送器 — 多从并发上行压测 (一键启动)。

在同一台 Jetson 上同时驱动多台从机 DS10, 用 threading.Barrier 让所有从机
在同一瞬间开始发送, 消除人工分终端启动的时差, 制造真正的并发上行。
帧格式与 ds10_slave_send.py 一致 (标准 Modbus 0x10 帧 + MARKER+seq 嵌数据区),
主机端用 ds10_master_recv.py 按站号对账即可。

用法:
  # 默认: 两台从机 ttyUSB1=站号1 / ttyUSB2=站号2, 各发 200 帧, 间隔 50ms
  python3 ds10_multi_slave_send.py

  # 自定义从机列表: 端口:站号 成对给出 (空格分隔)
  python3 ds10_multi_slave_send.py --slaves /dev/ttyUSB1:1 /dev/ttyUSB2:2

  # 三台从机、更高频、无限发送
  python3 ds10_multi_slave_send.py \
      --slaves /dev/ttyUSB1:1 /dev/ttyUSB2:2 /dev/ttyUSB3:3 \
      --interval 0.02 --count 0
"""

import argparse
import os
import sys
import threading
import time

import serial

MARKER = b"\xF1\xF1"     # 与 ds10_master_recv.py 约定一致


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_frame(station, seq, payload):
    """标准 Modbus 0x10 帧, 首字节站号, MARKER+seq 放数据区开头。"""
    data = MARKER + bytes(((seq >> 8) & 0xFF, seq & 0xFF)) + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def parse_slaves(items):
    """把 ['/dev/ttyUSB1:1', '/dev/ttyUSB2:2'] 解析为 [(port, station), ...]。"""
    out = []
    for it in items:
        if ":" not in it:
            raise ValueError(f"--slaves 每项须为 port:station, 得到 {it!r}")
        port, _, station = it.rpartition(":")
        sid = int(station)
        if not 1 <= sid <= 247:
            raise ValueError(f"站号须 1-247, 得到 {sid}")
        out.append((port, sid))
    return out


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 多从机并发发送")
    ap.add_argument("--slaves", nargs="+",
                    default=["/dev/ttyUSB1:1", "/dev/ttyUSB2:2"],
                    help="从机列表, 每项 port:station (默认 ttyUSB1:1 ttyUSB2:2)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--sizes", default="32,128,240",
                    help="逗号分隔的载荷字节数, 逐帧轮换 (默认 32,128,240)")
    ap.add_argument("--interval", type=float, default=0.05,
                    help="帧间隔秒数, 越小并发越密 (默认 0.05)")
    ap.add_argument("--count", type=int, default=200,
                    help="每台从机发送帧数, 0=无限 (默认 200)")
    return ap.parse_args()


class SlaveWorker(threading.Thread):
    """一台从机: 独占一个串口, 屏障同步后连续发送。"""

    def __init__(self, port, station, ser, sizes, interval, count, barrier, results):
        super().__init__(name=f"slave-{station}")
        self.port = port
        self.station = station
        self.ser = ser
        self.sizes = sizes
        self.interval = interval
        self.count = count
        self.barrier = barrier
        self.results = results
        self.stop_evt = threading.Event()

    def run(self):
        # 所有从机在此对齐, 同一瞬间放行 -> 真正的并发起点
        self.barrier.wait()
        seq = 0
        sent_bytes = 0
        t0 = time.monotonic()
        try:
            while not self.stop_evt.is_set() and (self.count == 0 or seq < self.count):
                size = self.sizes[seq % len(self.sizes)]
                frame = build_frame(self.station, seq, os.urandom(size))
                self.ser.write(frame)
                self.ser.flush()
                seq += 1
                sent_bytes += len(frame)
                if self.interval > 0:
                    time.sleep(self.interval)
        finally:
            dur = time.monotonic() - t0
            self.results[self.station] = (seq, sent_bytes, dur)


def main():
    args = parse_args()
    try:
        slaves = parse_slaves(args.slaves)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        return 1
    sizes = [max(0, int(x)) for x in args.sizes.split(",") if x.strip()]
    if not sizes:
        print("sizes 不能为空", file=sys.stderr)
        return 1

    # 先全部打开串口, 任一失败则整体退出 (避免只启动一部分从机)
    opened = []
    try:
        for port, sid in slaves:
            ser = serial.Serial(port, args.baud, timeout=0.1)
            opened.append((port, sid, ser))
            print(f"已打开 {port} @ {args.baud} 8N1 -> 站号 {sid}")
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        print("检查: 端口存在 (ls /dev/ttyUSB*)、未被占用、在 dialout 组。", file=sys.stderr)
        for _, _, ser in opened:
            ser.close()
        return 1

    n = len(opened)
    print(f"\n{n} 台从机就绪, 屏障同步后同时发送 | 载荷 {sizes} 轮换 | "
          f"间隔 {args.interval}s | {'无限' if args.count == 0 else str(args.count)+' 帧/台'}")
    print("Ctrl-C 停止")
    print("-" * 68)

    # 屏障容量 = 从机数 + 主线程, 主线程 wait 即为统一发令枪
    barrier = threading.Barrier(n + 1)
    results = {}
    workers = [
        SlaveWorker(port, sid, ser, sizes, args.interval, args.count, barrier, results)
        for port, sid, ser in opened
    ]
    for w in workers:
        w.start()

    t_start = time.monotonic()
    barrier.wait()          # 发令: 所有从机同时开跑
    print(f"[{time.strftime('%H:%M:%S')}] 全部从机同时开始发送")

    try:
        for w in workers:
            w.join()
    except KeyboardInterrupt:
        print("\n收到 Ctrl-C, 停止所有从机 ...")
        for w in workers:
            w.stop_evt.set()
        for w in workers:
            w.join(timeout=2)
    finally:
        for _, _, ser in opened:
            ser.close()
        dur = time.monotonic() - t_start
        print("\n" + "=" * 68)
        print(f"总耗时 {dur:.1f}s")
        for _, sid, _ in opened:
            if sid in results:
                frames, sbytes, sd = results[sid]
                rate = sbytes / sd if sd > 0 else 0
                print(f"  站号 {sid}: 发送 {frames} 帧 / {sbytes/1024:.1f}KB "
                      f"均速 {rate:.0f}B/s")
        print("所有串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
