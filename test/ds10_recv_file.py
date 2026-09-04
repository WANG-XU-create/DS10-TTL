#!/usr/bin/env python3
"""DS10 文件接收端 —— 接收分帧文件、按 seq 排序重组、写出。

用法:
  python3 ds10_recv_file.py --port /dev/ttyUSB1 --station 1 --out received.txt

接收到最后一帧 (is_last=1) 后自动停止并写文件。与源文件 diff 验证完整性。
"""

import argparse
import sys
import threading
import time

import serial

MARKER = b"\xF1\xF1"
MIN_FRAME = 6


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def extract_frames(buf):
    """提取并验证 Modbus 0x10 帧,返回 (帧列表, 剩余buf)。帧 = (station, seq, is_last, payload)。"""
    frames = []
    while len(buf) >= MIN_FRAME:
        station = buf[0]
        if buf[1] != 0x10:
            del buf[0]
            continue
        body_len = 7 + buf[6]
        if len(buf) < body_len + 2:
            break
        frame_bytes = bytes(buf[:body_len + 2])
        calc = modbus_crc16(frame_bytes[:-2])
        recv = frame_bytes[-2:]
        if calc != recv:
            del buf[0]
            continue
        del buf[:body_len + 2]

        data = frame_bytes[7:body_len]
        if len(data) < 7 or data[:2] != MARKER:
            continue
        seq = (data[2] << 8) | data[3]
        is_last = bool(data[4])
        payload_len = (data[5] << 8) | data[6]
        payload = data[7:7+payload_len]  # 只取真实长度，去掉填充
        frames.append((station, seq, is_last, payload))
    return frames, buf


class Receiver(threading.Thread):
    def __init__(self, ser, target_station):
        super().__init__(daemon=True)
        self._ser = ser
        self._station = target_station
        self._chunks = {}      # {seq: (is_last, payload)}
        self._done = False
        self._stop_flag = False
        self._lock = threading.Lock()

    def run(self):
        buf = bytearray()
        while not self._stop_flag:
            if self._ser.in_waiting:
                buf.extend(self._ser.read(self._ser.in_waiting))
                frames, buf = extract_frames(buf)
                with self._lock:
                    for station, seq, is_last, payload in frames:
                        if station != self._station:
                            continue
                        if seq not in self._chunks:
                            self._chunks[seq] = (is_last, payload)
                            print(f"  [收到]  seq={seq}  {len(payload)}B  "
                                  f"{'[最后一帧]' if is_last else ''}")
                        if is_last:
                            self._done = True
                            return
            else:
                time.sleep(0.01)

    def stop(self):
        self._stop_flag = True

    def is_done(self):
        with self._lock:
            return self._done

    def get_chunks(self):
        with self._lock:
            return dict(self._chunks)


def main():
    ap = argparse.ArgumentParser(description="DS10 文件接收端")
    ap.add_argument("--port", required=True, help="串口设备 (如 /dev/ttyUSB1)")
    ap.add_argument("--station", type=int, default=1, help="接收站号 (默认 1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--out", required=True, help="输出文件路径")
    ap.add_argument("--timeout", type=float, default=60.0, help="超时秒 (默认 60)")
    args = ap.parse_args()

    print(f"站号: {args.station}  串口: {args.port} @ {args.baud} 8N1")
    print(f"接收中... (超时 {args.timeout}s 或收到最后一帧则停止)")
    print("=" * 68)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        return 1

    rx = Receiver(ser, args.station)
    rx.start()

    start = time.time()
    while time.time() - start < args.timeout:
        if rx.is_done():
            break
        time.sleep(0.2)

    rx.stop()
    rx.join(timeout=1)
    ser.close()

    chunks_dict = rx.get_chunks()
    if not chunks_dict:
        print("\n未收到任何帧 ❌", file=sys.stderr)
        return 1

    seqs = sorted(chunks_dict.keys())
    expected = list(range(len(seqs)))
    missing = [s for s in expected if s not in seqs]
    has_last = any(is_last for is_last, _ in chunks_dict.values())

    print("=" * 68)
    print(f"收到 {len(seqs)} 帧: seq {seqs[0]}..{seqs[-1]}")
    if missing:
        print(f"⚠️ 缺失 seq: {missing}")
    if not has_last:
        print("⚠️ 未收到最后一帧标记 (可能传输未完成或超时)")

    # 按 seq 排序重组
    content = b"".join(chunks_dict[s][1] for s in seqs)
    with open(args.out, "wb") as f:
        f.write(content)

    print(f"✅ 已写入: {args.out}  ({len(content)} B)")
    print(f"\n用 diff/cmp 验证完整性:")
    print(f"  diff <源文件> {args.out}")
    print(f"  cmp <源文件> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
