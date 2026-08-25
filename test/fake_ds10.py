"""假 DS10:在 PTY 的 master 端讲 AT,供配置脚本端到端测试。

被测脚本打开 slave 路径 (os.ttyname) 作为串口。按 PTY 规则:本假设备持有
master 端,并把 slave 端尚无打开者时出现的瞬态 EIO/EAGAIN 视为非致命,轮询
而不是退出(复用 modbus_rtu_bus_driver 的 PTY 先例)。
"""

import os
import select
import threading
import time

try:
    import tty
except ImportError:  # pragma: no cover
    tty = None


class FakeDS10:
    def __init__(self, devinfo=("DS10-TTL", "DS1000000008", "V1.0.0", "15"),
                 error_on=None):
        self.devinfo = tuple(devinfo)
        self.error_on = dict(error_on or {})  # 命令(str) -> (code, reason)
        self.seen = []                        # 收到的命令,按序记录
        self._master_fd, self._slave_fd = os.openpty()
        self.port = os.ttyname(self._slave_fd)
        if tty is not None:
            try:
                tty.setraw(self._master_fd)
            except Exception:
                pass
        # 关掉我们这端的 slave 句柄,让脚本成为 slave 的唯一打开者。
        os.close(self._slave_fd)
        self._stop = threading.Event()
        self._buf = bytearray()
        self._entered = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)
        try:
            os.close(self._master_fd)
        except OSError:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def _run(self):
        while not self._stop.is_set():
            try:
                r, _, _ = select.select([self._master_fd], [], [], 0.05)
                if not r:
                    continue
                chunk = os.read(self._master_fd, 4096)
            except OSError:
                # slave 端尚无打开者时的 EIO/EAGAIN:瞬态,继续轮询。
                time.sleep(0.02)
                continue
            if not chunk:
                time.sleep(0.02)
                continue
            self._buf += chunk
            self._consume()

    def _consume(self):
        # 触发串无终止符,出现在任意位置都吞掉。
        while b"+++" in self._buf:
            self._buf = bytearray(self._buf.replace(b"+++", b"", 1))
            self._entered = True
        while b"\n" in self._buf:
            line, _, rest = self._buf.partition(b"\n")
            self._buf = bytearray(rest)
            cmd = line.decode(errors="replace").strip("\r").strip()
            if cmd:
                self.seen.append(cmd)
                self._handle(cmd)

    def _handle(self, cmd):
        if cmd in self.error_on:
            code, reason = self.error_on[cmd]
            self._send("+DS10ERR:%s,%s" % (code, reason))
            self._send("ERROR")
            return
        if cmd == "AT":
            self._send("OK")
        elif cmd == "AT+DEVINFO?":
            self._send("+DEVINFO:" + ",".join(self.devinfo))
            self._send("OK")
        elif cmd == "AT+CFG_NEW":
            self._send("+CFG_NEW")
            self._send("+CFG_STATE:1,0")
            self._send("OK")
        elif cmd.startswith("AT+CFG_ROLE="):
            self._send("+CFG_DRAFT:1")
            self._send("OK")
        elif cmd.startswith("AT+CFG_CH="):
            self._send("+CFG_DRAFT:1")
            self._send("OK")
        elif cmd == "AT+CFG_SAVE":
            self._send("+CFG_SAVE:REBOOTING")
            self._send("OK")
        else:
            self._send("+DS10ERR:1,UNKNOWN_CMD")
            self._send("ERROR")

    def _send(self, line):
        os.write(self._master_fd, (line + "\r\n").encode())
