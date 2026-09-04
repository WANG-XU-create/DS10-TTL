#!/usr/bin/env python3
"""DS10 主从双向通信冲突测试 (三口同机, 共用时钟)。

场景: 主机向从机1发送数据 (下行), 同时从机2向主机发送数据 (上行)。
目的: 测 DS10 无线链路在反向双工时是否冲突——无线若是半双工, 主机下行突发
      期间会听不到上行, 上行帧丢失; 若全双工/调度良好, 两向互不影响。

三台 DS10 均挂同一台 Jetson, 单进程控制三个串口、共用 time.monotonic():
  下行: 主机口 --TX 站号1--> (无线) --> 从机1口 RX
  上行: 从机2口 --TX 站号2--> (无线) --> 主机口 RX
主机口同时收发 (UART 全双工, 非瓶颈)。

方法: 必须有基线才能判定"冲突"。分三阶段, 每阶段统计各方向到达率:
  阶段1 仅下行  -> 下行基线
  阶段2 仅上行  -> 上行基线
  阶段3 并发    -> 与基线对照; 明显下降即为冲突
并发阶段用 threading.Barrier 让收发线程同一瞬间放行, 制造真正的双向同时。

用法:
  python3 ds10_bidir_collision.py \
      --master /dev/ttyUSB0 --slave1 /dev/ttyUSB1 --slave2 /dev/ttyUSB2 \
      --count 200 --interval 0.05
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
DOWN_STATION = 1     # 下行: 主机发给从机1, 帧首字节站号1
UP_STATION = 2       # 上行: 从机2发给主机, 帧首字节站号2


def modbus_crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def build_text_payload(size):
    """生成可读文本载荷 (循环填充, 便于目视验证)。"""
    TEXT = b"DS10Test_"
    return (TEXT * (size // len(TEXT) + 1))[:size]


def build_frame(station, seq, payload):
    """标准 Modbus 0x10 帧, MARKER+seq(2B) 放数据区开头 (与 recv 对账一致)。"""
    data = MARKER + bytes(((seq >> 8) & 0xFF, seq & 0xFF)) + payload
    if len(data) % 2:
        data += b"\x00"
    qty = (len(data) // 2) & 0xFFFF
    body = bytes((station, 0x10, 0x00, 0x00,
                  (qty >> 8) & 0xFF, qty & 0xFF, len(data) & 0xFF)) + data
    return body + modbus_crc16(body)


def seq_of(frame):
    data_region = frame[7:-2] if len(frame) >= 9 else b""
    if data_region[:2] == MARKER and len(data_region) >= 4:
        return (data_region[2] << 8) | data_region[3]
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


def tally(seqs):
    """从收到的 seq 列表算 到达率/丢帧/重复/乱序 (发送端 seq 连续 0..count-1)。"""
    if not seqs:
        return {"recv": 0, "unique": 0, "dup": 0, "lo": None, "hi": None, "gaps": 0}
    seen = set()
    dup = 0
    for s in seqs:
        if s in seen:
            dup += 1
        seen.add(s)
    lo, hi = min(seen), max(seen)
    gaps = (hi - lo + 1) - len(seen)   # 区间内缺失的 seq 个数
    return {"recv": len(seqs), "unique": len(seen), "dup": dup,
            "lo": lo, "hi": hi, "gaps": gaps}


class Sender(threading.Thread):
    """从一个串口发送 count 帧, seq 连续。barrier 到齐后同一瞬间开跑。"""

    def __init__(self, ser, station, count, interval, payload, barrier, label):
        super().__init__(daemon=True)
        self.ser = ser
        self.station = station
        self.count = count
        self.interval = interval
        self.payload = payload
        self.barrier = barrier
        self.label = label
        self.sent = 0

    def run(self):
        if self.barrier is not None:
            self.barrier.wait()
        for seq in range(self.count):
            self.ser.write(build_frame(self.station, seq, self.payload))
            self.ser.flush()
            self.sent += 1
            if self.interval > 0:
                time.sleep(self.interval)


class Receiver(threading.Thread):
    """持续从一个串口切帧, 按站号收集 seq。stop() 结束。"""

    def __init__(self, ser, want_station, label):
        super().__init__(daemon=True)
        self.ser = ser
        self.want_station = want_station
        self.label = label
        self.seqs = []
        self.stop_evt = threading.Event()

    def run(self):
        buf = bytearray()
        while not self.stop_evt.is_set():
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
                frames, buf = extract_frames(buf)
                for fr in frames:
                    if fr[0] != self.want_station:
                        continue
                    s = seq_of(fr)
                    if s is not None:
                        self.seqs.append(s)
            else:
                time.sleep(0.0005)

    def snapshot(self):
        return list(self.seqs)

    def reset(self):
        self.seqs = []

    def stop(self):
        self.stop_evt.set()


def report(title, count, down_seqs, up_seqs):
    """打印一个阶段的双向统计。down/up 任一为 None 表示该方向本阶段未跑。"""
    print(f"\n【{title}】 (每方向发送 {count} 帧)")
    for name, seqs in (("下行 主机->从机1 (站号1)", down_seqs),
                       ("上行 从机2->主机 (站号2)", up_seqs)):
        if seqs is None:
            continue
        t = tally(seqs)
        if t["unique"] == 0:
            print(f"  {name}: 收 0 帧 ❌")
            continue
        rate = t["unique"] / count * 100
        cover = f"seq {t['lo']}..{t['hi']}"
        extra = f" 丢{t['gaps']}" if t["gaps"] else ""
        extra += f" 重复{t['dup']}" if t["dup"] else ""
        print(f"  {name}: 唯一 {t['unique']}/{count} 到达率 {rate:.1f}% "
              f"({cover}{extra})")
    return {"down": tally(down_seqs) if down_seqs is not None else None,
            "up": tally(up_seqs) if up_seqs is not None else None}


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 主从双向通信冲突测试 (三口同机)")
    ap.add_argument("--master", default="/dev/ttyUSB0", help="主机口 (默认 ttyUSB0)")
    ap.add_argument("--slave1", default="/dev/ttyUSB1", help="从机1口, 收下行 (默认 ttyUSB1)")
    ap.add_argument("--slave2", default="/dev/ttyUSB2", help="从机2口, 发上行 (默认 ttyUSB2)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--count", type=int, default=200, help="每方向发送帧数 (默认 200)")
    ap.add_argument("--interval", type=float, default=0.05, help="发送间隔秒 (默认 0.05)")
    ap.add_argument("--size", type=int, default=32, help="每帧载荷字节数 (默认 32)")
    ap.add_argument("--settle", type=float, default=1.0,
                    help="每阶段发送结束后等待收尾秒数 (默认 1.0)")
    return ap.parse_args()


def run_phase(title, count, interval, payload,
              m_ser, s1_ser, s2_ser, m_rx, s1_rx, settle,
              do_down, do_up):
    """跑一个阶段。do_down/do_up 决定该方向是否发送。返回 (down_seqs, up_seqs)。"""
    m_rx.reset()
    s1_rx.reset()
    m_ser.reset_input_buffer()
    s1_ser.reset_input_buffer()

    senders = []
    n_send = (1 if do_down else 0) + (1 if do_up else 0)
    barrier = threading.Barrier(n_send) if n_send > 1 else None
    if do_down:
        senders.append(Sender(m_ser, DOWN_STATION, count, interval, payload, barrier, "down"))
    if do_up:
        senders.append(Sender(s2_ser, UP_STATION, count, interval, payload, barrier, "up"))

    for s in senders:
        s.start()
    for s in senders:
        s.join()
    time.sleep(settle)   # 等在途帧收完

    down_seqs = s1_rx.snapshot() if do_down else None
    up_seqs = m_rx.snapshot() if do_up else None
    return report(title, count, down_seqs, up_seqs)


def main():
    args = parse_args()
    payload = build_text_payload(max(0, args.size))
    try:
        m_ser = serial.Serial(args.master, args.baud, timeout=0.1)
        s1_ser = serial.Serial(args.slave1, args.baud, timeout=0.1)
        s2_ser = serial.Serial(args.slave2, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        print("检查三个口都存在、未被占用、在 dialout 组; CH340 无序列号注意别撞车。",
              file=sys.stderr)
        return 1

    print(f"主机 {m_ser.port} | 从机1 {s1_ser.port} | 从机2 {s2_ser.port} @ {args.baud} 8N1")
    print(f"下行 主机->从机1(站号{DOWN_STATION}) | 上行 从机2->主机(站号{UP_STATION})")
    print(f"每方向 {args.count} 帧, 载荷 {args.size}B, 间隔 {args.interval*1000:.0f}ms")
    print("=" * 68)

    # 主机口收上行(站号2), 从机1口收下行(站号1)
    m_rx = Receiver(m_ser, UP_STATION, "master-rx")
    s1_rx = Receiver(s1_ser, DOWN_STATION, "slave1-rx")
    m_rx.start()
    s1_rx.start()

    try:
        base_down = run_phase("阶段1 仅下行 (基线)", args.count, args.interval, payload,
                              m_ser, s1_ser, s2_ser, m_rx, s1_rx, args.settle,
                              do_down=True, do_up=False)
        base_up = run_phase("阶段2 仅上行 (基线)", args.count, args.interval, payload,
                            m_ser, s1_ser, s2_ser, m_rx, s1_rx, args.settle,
                            do_down=False, do_up=True)
        concur = run_phase("阶段3 双向并发", args.count, args.interval, payload,
                          m_ser, s1_ser, s2_ser, m_rx, s1_rx, args.settle,
                          do_down=True, do_up=True)
    except KeyboardInterrupt:
        print("\n中断。")
        concur = base_up = None
    finally:
        m_rx.stop()
        s1_rx.stop()
        m_rx.join(timeout=1)
        s1_rx.join(timeout=1)
        m_ser.close()
        s1_ser.close()
        s2_ser.close()

    if concur and concur["down"] and concur["up"]:
        print("\n" + "=" * 68)
        print("冲突判定 (并发 vs 基线)")
        print("-" * 68)
        bd = base_down["down"]["unique"] / args.count * 100
        bu = base_up["up"]["unique"] / args.count * 100
        cd = concur["down"]["unique"] / args.count * 100
        cu = concur["up"]["unique"] / args.count * 100
        print(f"  下行: 基线 {bd:.1f}%  ->  并发 {cd:.1f}%  (Δ {cd-bd:+.1f})")
        print(f"  上行: 基线 {bu:.1f}%  ->  并发 {cu:.1f}%  (Δ {cu-bu:+.1f})")
        worst = min(cd - bd, cu - bu)
        if worst >= -3:
            print("  结论: 无明显冲突 ✅ 双向并发到达率与基线相当 (全双工/调度良好)。")
        elif worst >= -15:
            print("  结论: 轻度冲突 ⚠️ 并发下某方向到达率小幅下降。")
        else:
            print("  结论: 明显冲突 ❌ 并发下某方向到达率大幅下降 (疑似半双工争用)。")
    print("\n串口已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
