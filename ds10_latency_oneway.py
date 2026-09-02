#!/usr/bin/env python3
"""DS10 单向延迟测试 (主/从同机, 共用时钟)。

前提: 主机 DS10 与从机 DS10 同挂一台 Jetson (调试布局)。主机口发送、从机口接收,
两个串口在同一进程里共用 time.monotonic() 时钟, 因此可直接测单向延迟而无需两机
时钟同步——这是单向测量最干净的方式, 且不受 ping-pong 往返放大影响。

流程: 发送线程从主机口发探针帧(带唯一 id, 记 t0) -> DS10 无线 -> 接收线程从从机口
收到该 id(记 t1) -> 单向延迟 = t1 - t0。可选扣除单程串口传输时间得纯无线延迟。

用法:
  # 默认: 主机口 ttyUSB0 发 -> 从机口 ttyUSB1 收, 站号1, 尺寸 32/240/1400, 各 50 次
  python3 ds10_latency_oneway.py --tx /dev/ttyUSB0 --rx /dev/ttyUSB1 --station 1

  # 大帧稀疏发送 (间隔大, 避免帧堆叠), 更多样本
  python3 ds10_latency_oneway.py --sizes 1400 --rounds 30 --interval 0.5
"""

import argparse
import os
import sys
import threading
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
    payload = build_text_payload(size, probe_id)
    data = MARKER + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def probe_id_of(frame):
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


def serial_ms(frame_bytes, baud):
    return frame_bytes * 10.0 / baud * 1000.0


class RxWorker(threading.Thread):
    """从机口接收线程: 切帧, 记录每个 probe_id 的到达时刻 (共用主时钟)。"""

    def __init__(self, ser, station):
        super().__init__(daemon=True)
        self.ser = ser
        self.station = station
        self.arrivals = {}          # probe_id -> t1 (monotonic)
        self.lock = threading.Lock()
        self.stop_evt = threading.Event()

    def run(self):
        buf = bytearray()
        while not self.stop_evt.is_set():
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
                t1 = time.monotonic()
                frames, buf = extract_frames(buf)
                for fr in frames:
                    if fr[0] != self.station:
                        continue
                    pid = probe_id_of(fr)
                    if pid is not None:
                        with self.lock:
                            self.arrivals.setdefault(pid, t1)
            else:
                time.sleep(0.0005)

    def get(self, pid):
        with self.lock:
            return self.arrivals.get(pid)

    def stop(self):
        self.stop_evt.set()


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 单向延迟测试 (主/从同机)")
    ap.add_argument("--tx", default="/dev/ttyUSB0", help="主机发送口 (默认 /dev/ttyUSB0)")
    ap.add_argument("--rx", default="/dev/ttyUSB1", help="从机接收口 (默认 /dev/ttyUSB1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--station", type=int, default=1, help="站号 (默认 1)")
    ap.add_argument("--sizes", default="32,240,1400",
                    help="逗号分隔的探针载荷字节数 (默认 32,240,1400)")
    ap.add_argument("--rounds", type=int, default=50, help="每种尺寸测量次数 (默认 50)")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="单次等待到达超时秒数 (默认 2.0)")
    ap.add_argument("--interval", type=float, default=0.2,
                    help="两次探针间隔秒数, 避免帧堆叠 (默认 0.2)")
    return ap.parse_args()


def summarize(name, lats, frame_len, baud):
    """打印单向延迟统计, 并扣除单程串口传输时间得纯无线延迟。"""
    if not lats:
        print(f"  {name}: 无有效样本 (全部超时/丢失)")
        return
    ms = sorted(x * 1000 for x in lats)
    n = len(ms)
    mean = sum(ms) / n
    p50 = ms[n // 2]
    p95 = ms[min(n - 1, int(n * 0.95))]
    stx = serial_ms(frame_len, baud)   # 单向只含 1 段串口 TX (t0 在 write 后, t1 在 rx read)
    # 说明: t0 记于主机 write() 后, t1 记于从机 read() 到达; 单向延迟含
    #   从机侧串口接收传输 (1 段) + 无线 + DS10 处理。扣 1 段串口得近似无线。
    link_mean = max(0.0, mean - stx)
    link_p50 = max(0.0, p50 - stx)
    print(f"  {name} (整帧 {frame_len}B):")
    print(f"    单向延迟 : 均 {mean:7.2f}ms  中位 {p50:7.2f}ms  p95 {p95:7.2f}ms  "
          f"最小 {ms[0]:7.2f}ms  最大 {ms[-1]:7.2f}ms")
    print(f"    扣串口RX : -{stx:.2f}ms (从机侧接收传输) -> 纯无线 ≈ 均 {link_mean:.2f}ms "
          f"中位 {link_p50:.2f}ms")


def main():
    args = parse_args()
    sizes = [max(6, int(x)) for x in args.sizes.split(",") if x.strip()]
    if not sizes:
        print("sizes 不能为空", file=sys.stderr)
        return 1
    try:
        tx = serial.Serial(args.tx, args.baud, timeout=0.1)
        rx = serial.Serial(args.rx, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        print("检查: 两口都存在、未被占用、在 dialout 组。", file=sys.stderr)
        return 1

    print(f"tx={tx.port}  rx={rx.port}  @ {args.baud} 8N1  站号 {args.station}")
    print(f"尺寸 {sizes} 各测 {args.rounds} 次 | 超时 {args.timeout}s | 单向, 共用时钟")
    print("-" * 68)
    rx.reset_input_buffer()

    worker = RxWorker(rx, args.station)
    worker.start()

    probe_id = 0
    results = {}
    lost = {}
    frame_lens = {}
    try:
        for size in sizes:
            lats = []
            miss = 0
            for _ in range(args.rounds):
                probe_id += 1
                frame = build_probe(args.station, probe_id, size)
                frame_lens[size] = len(frame)
                t0 = time.monotonic()
                tx.write(frame)
                tx.flush()
                deadline = t0 + args.timeout
                arrived = None
                while time.monotonic() < deadline:
                    t1 = worker.get(probe_id)
                    if t1 is not None:
                        arrived = t1 - t0
                        break
                    time.sleep(0.0005)
                if arrived is None:
                    miss += 1
                else:
                    lats.append(arrived)
                if args.interval > 0:
                    time.sleep(args.interval)
            results[size] = lats
            lost[size] = miss
            print(f"[{size:>4}B] 完成 {len(lats)}/{args.rounds} (丢失 {miss})")
    except KeyboardInterrupt:
        print("\n中断。")
    finally:
        worker.stop()
        worker.join(timeout=1)
        tx.close()
        rx.close()

    print("\n" + "=" * 68)
    print("单向延迟统计 (主机口发 -> 从机口收, 共用时钟)")
    print("-" * 68)
    for size in sizes:
        summarize(f"{size:>4}B", results.get(size, []), frame_lens.get(size, size), args.baud)
        if lost.get(size):
            print(f"    (丢失/超时 {lost[size]} 次)")
    print("\n注: 单向延迟 = 主机 write 后到从机 read 到达; 含从机侧串口接收 + 无线 +")
    print("    DS10 处理。扣 1 段串口接收得近似纯无线延迟。")
    print("串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

