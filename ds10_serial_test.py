#!/usr/bin/env python3
"""DS10-TTL 串口通信测试工具 (pyserial)。

用法:
  # 交互式:键盘输入的行发送出去,收到的数据实时打印
  python3 ds10_serial_test.py

  # 指定串口/波特率
  python3 ds10_serial_test.py -p /dev/ttyUSB0 -b 115200

  # 只监听,不发送(观察对端是否主动上报数据)
  python3 ds10_serial_test.py --monitor

  # 发送一段文本后读取 2 秒回复,然后退出(适合脚本化验证)
  python3 ds10_serial_test.py --send "AT" --wait 2

  # 以十六进制发送(空格分隔的字节)
  python3 ds10_serial_test.py --send "01 03 00 00 00 01" --hex --wait 2
"""

import argparse
import sys
import threading
import time

import serial


def parse_args():
    ap = argparse.ArgumentParser(description="DS10-TTL 串口通信测试")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0", help="串口设备 (默认 /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--monitor", action="store_true", help="只监听接收,不发送")
    ap.add_argument("--send", metavar="DATA", help="发送一次数据后读取回复")
    ap.add_argument("--hex", action="store_true", help="--send 的内容按十六进制字节解析")
    ap.add_argument("--wait", type=float, default=2.0, help="--send 后等待回复的秒数")
    ap.add_argument("--no-newline", action="store_true", help="发送时不追加换行")
    return ap.parse_args()


def encode_payload(data, as_hex, add_newline):
    if as_hex:
        return bytes(int(x, 16) for x in data.split())
    payload = data.encode("utf-8", errors="replace")
    if add_newline:
        payload += b"\r\n"
    return payload


def dump(prefix, chunk):
    text = chunk.decode("utf-8", errors="replace")
    hexs = " ".join(f"{b:02X}" for b in chunk)
    print(f"{prefix} text: {text!r}")
    print(f"{prefix} hex : {hexs}")


def read_loop(ser, stop_event):
    while not stop_event.is_set():
        n = ser.in_waiting
        if n:
            dump("<-", ser.read(n))
        else:
            time.sleep(0.02)


def main():
    args = parse_args()
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备是否存在 (ls /dev/ttyUSB*)、权限 (dialout 组)、是否被占用。", file=sys.stderr)
        return 1

    print(f"已打开 {ser.port} @ {ser.baudrate} 8N1。Ctrl-C 退出。")

    if args.send is not None:
        payload = encode_payload(args.send, args.hex, not args.no_newline)
        ser.reset_input_buffer()
        ser.write(payload)
        ser.flush()
        dump("->", payload)
        deadline = time.time() + args.wait
        got = bytearray()
        while time.time() < deadline:
            n = ser.in_waiting
            if n:
                got += ser.read(n)
            else:
                time.sleep(0.02)
        if got:
            dump("<-", bytes(got))
        else:
            print("<- (无回复)")
        ser.close()
        return 0

    stop_event = threading.Event()
    reader = threading.Thread(target=read_loop, args=(ser, stop_event), daemon=True)
    reader.start()
    try:
        if args.monitor:
            while True:
                time.sleep(0.5)
        else:
            for line in sys.stdin:
                payload = encode_payload(line.rstrip("\n"), False, not args.no_newline)
                ser.write(payload)
                ser.flush()
                dump("->", payload)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        reader.join(timeout=1)
        ser.close()
        print("\n已关闭串口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
