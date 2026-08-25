#!/usr/bin/env python3
"""DS10 星闪 DTU 配置工具 (pyserial)。

进入 AT 会话,读取设备信息 (型号/SN/版本/最大从机数)。SN 供主机 --bind 使用。

用法:
  # 读取设备信息 (建议用 by-id 路径,避免 ttyUSB 序号漂移)
  python3 ds10_config.py --port /dev/serial/by-id/usb-XXXX --info

退出码:
  0  成功
  2  串口打开/连接失败
  3  设备返回 +DS10ERR
"""

import argparse
import sys
import time

import serial

EXIT_OK = 0
EXIT_SERIAL = 2
EXIT_DS10ERR = 3

TRIGGER = b"+++"          # 进入 AT 会话的触发串 (默认)
TERM = b"\r\n"            # 命令行终止符
GUARD = 0.6              # +++ 前后各需的空闲守护时间 (文档要求 ≥0.5s)


class DS10Error(Exception):
    def __init__(self, code, reason):
        super().__init__(f"+DS10ERR:{code},{reason}")
        self.code = code
        self.reason = reason


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="DS10 星闪 DTU 配置工具")
    ap.add_argument("-p", "--port", default="/dev/ttyUSB0",
                    help="串口设备,建议用 /dev/serial/by-id/ 路径 (默认 /dev/ttyUSB0)")
    ap.add_argument("-b", "--baud", type=int, default=115200, help="波特率 (默认 115200)")
    ap.add_argument("--info", action="store_true", help="读取并打印设备信息 (型号/SN/版本/最大从机数)")
    ap.add_argument("--timeout", type=float, default=2.0, help="单条命令等待响应的秒数 (默认 2.0)")
    return ap.parse_args(argv)


def dump(prefix, text):
    print(f"{prefix} {text!r}")


class ATSession:
    """在已打开的串口上进行 AT 收发。响应以终止行 (OK / ERROR) 判定完成。"""

    def __init__(self, ser, timeout=2.0):
        self.ser = ser
        self.timeout = timeout

    def enter(self):
        self.ser.reset_input_buffer()
        time.sleep(GUARD)  # +++ 前的空闲守护 (文档要求 ≥0.5s)
        self.ser.write(TRIGGER)
        self.ser.flush()
        dump("->", TRIGGER)
        time.sleep(GUARD)  # +++ 后的空闲守护 (文档要求 ≥0.5s)
        self.command("AT")

    def command(self, cmd):
        self.ser.write(cmd.encode() + TERM)
        self.ser.flush()
        dump("->", cmd)
        lines = self._read_response()
        for line in lines:
            dump("<-", line)
            if line.startswith("+DS10ERR:"):
                body = line[len("+DS10ERR:"):]
                code, _, reason = body.partition(",")
                raise DS10Error(code.strip(), reason.strip())
        return lines

    def _read_response(self):
        deadline = time.time() + self.timeout
        buf = bytearray()
        lines = []
        while time.time() < deadline:
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
                while b"\n" in buf:
                    raw, _, rest = buf.partition(b"\n")
                    buf = bytearray(rest)
                    line = raw.decode(errors="replace").strip("\r").strip()
                    if not line:
                        continue
                    lines.append(line)
                    if line in ("OK", "ERROR"):
                        return lines
            else:
                time.sleep(0.02)
        return lines


def read_devinfo(session):
    for line in session.command("AT+DEVINFO?"):
        if line.startswith("+DEVINFO:"):
            parts = line[len("+DEVINFO:"):].split(",")
            keys = ["型号", "SN", "版本", "最大从机数"]
            return dict(zip(keys, [p.strip() for p in parts]))
    return {}


def main(argv=None):
    args = parse_args(argv)
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"打开 {args.port} 失败: {e}", file=sys.stderr)
        print("检查: 设备是否存在、权限 (dialout 组)、是否被占用、by-id 路径是否正确。",
              file=sys.stderr)
        return EXIT_SERIAL

    try:
        session = ATSession(ser, timeout=args.timeout)
        session.enter()
        if args.info:
            info = read_devinfo(session)
            print("设备信息:")
            for k, v in info.items():
                print(f"  {k}: {v}")
    except DS10Error as e:
        print(f"设备返回错误: {e}", file=sys.stderr)
        return EXIT_DS10ERR
    finally:
        ser.close()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
