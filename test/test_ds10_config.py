"""ds10_config.py 的端到端测试,经由 PTY 上的假 DS10 驱动 CLI。

seam:被测脚本操作的串口边界。测试只观察脚本发出的 AT 帧和它的退出码,
不触碰内部函数。
"""

import pytest

from fake_ds10 import FakeDS10

ds10_config = pytest.importorskip("ds10_config")


def test_devinfo_happy_path_enters_at_and_prints_sn(capsys):
    with FakeDS10(devinfo=("DS10-TTL", "DS1000000008", "V1.0.0", "15")) as dev:
        rc = ds10_config.main(["--port", dev.port, "--info"])

    assert rc == 0
    # 进入 AT 会话后先确认会话,再查设备信息。
    assert dev.seen == ["AT", "AT+DEVINFO?"]
    out = capsys.readouterr().out
    assert "DS1000000008" in out
    assert "DS10-TTL" in out


def test_devinfo_aborts_on_ds10err(capsys):
    with FakeDS10(error_on={"AT+DEVINFO?": ("3", "BUSY")}) as dev:
        rc = ds10_config.main(["--port", dev.port, "--info"])

    assert rc != 0
    err = capsys.readouterr().err
    assert "BUSY" in err or "DS10ERR" in err


def test_open_failure_reports_and_nonzero_exit(capsys):
    rc = ds10_config.main(["--port", "/dev/does-not-exist-ds10", "--info"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "打开" in err or "失败" in err
