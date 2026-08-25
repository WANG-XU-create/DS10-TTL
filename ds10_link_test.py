#!/usr/bin/env python3
"""DS10 星闪链路测试:两台 DTU 都接在本机,验证无线端到端通信。

一个口发送,另一个口接收,校验数据是否原样透传。默认双向各测一轮。

用法:
  # 用默认口 (ttyUSB0 <-> ttyUSB1) 和波特率 115200 测试
  python3 ds10_link_test.py

  # 指定串口与波特率
  python3 ds10_link_test.py --a /dev/ttyUSB0 --b /dev/ttyUSB1 -b 115200

  # 只测 A->B 单方向
  python3 ds10_link_test.py --oneway

  # 多发几轮看稳定性
  python3 ds10_link_test.py --rounds 10
"""

import argparse
import sys
import time

import serial


def parse_args():
    ap = argparse.ArgumentParser(description="DS10 星闪双口链路测试")
    ap.add_argument("--a", default="/dev/ttyUSB0", help="A 端串口 (默认 /dev/ttyUSB0)")
    ap.add_argument("--b", dest="port_b", default="/dev/ttyUSB1", help="B 端串口 (默认 /dev/ttyUSB1)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--rounds", type=int, default=3, help="每个方向测试轮数 (默认 3)")
    ap.add_argument("--oneway", action="store_true", help="只测 A->B")
    ap.add_argument("--wait", type=float, default=1.0, help="每轮等待接收的秒数 (默认 1.0)")
    return ap.parse_args()


def drain(ser, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        if ser.in_waiting:
            ser.read(ser.in_waiting)
        else:
            time.sleep(0.02)


def recv_within(ser, deadline):
    got = bytearray()
    while time.time() < deadline:
        n = ser.in_waiting
        if n:
            got += ser.read(n)
        else:
            time.sleep(0.02)
    return bytes(got)


def one_transfer(tx, rx, payload, wait):
    tx.reset_input_buffer()
    rx.reset_input_buffer()
    drain(rx, 0.2)
    tx.write(payload)
    tx.flush()
    return recv_within(rx, time.time() + wait)


def run_direction(tx, rx, label, rounds, wait):
    ok = 0
    for i in range(1, rounds + 1):
        payload = f"DS10-LINK {label} #{i} {time.time():.3f}\n".encode()
        got = one_transfer(tx, rx, payload, wait)
        if got == payload:
            print(f"[{label}] 第 {i} 轮: OK  ({len(got)} 字节原样收到)")
            ok += 1
        elif got:
            print(f"[{label}] 第 {i} 轮: 收到但不一致")
            print(f"        发送: {payload!r}")
            print(f"        接收: {got!r}")
        else:
            print(f"[{label}] 第 {i} 轮: 超时,未收到数据")
    return ok


def main():
    args = parse_args()
    try:
        a = serial.Serial(args.a, args.baud, timeout=0.1)
        b = serial.Serial(args.port_b, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开串口失败: {e}", file=sys.stderr)
        print("检查: 两个设备节点是否都存在、权限 (dialout)、是否被 minicom 等占用。", file=sys.stderr)
        return 1

    print(f"A={a.port}  B={b.port}  @ {args.baud} 8N1")
    print("提示:两端 DTU 需已配对且波特率一致,否则无线链路不通。\n")

    total_ok = 0
    total = 0

    n = run_direction(a, b, "A->B", args.rounds, args.wait)
    total_ok += n
    total += args.rounds

    if not args.oneway:
        print()
        n = run_direction(b, a, "B->A", args.rounds, args.wait)
        total_ok += n
        total += args.rounds

    a.close()
    b.close()

    print(f"\n结果: {total_ok}/{total} 轮成功。")
    if total_ok == 0:
        print("全部失败,排查方向: 波特率不一致 / 两端未配对 / TX-RX 接反 / 供电不足。")
        return 2
    if total_ok < total:
        print("部分成功,可能是无线丢包或供电不稳,可加大 --wait 或降低波特率再测。")
        return 3
    print("链路通畅。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
