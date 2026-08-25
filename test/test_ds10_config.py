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


def test_role_master_creates_draft_and_saves(capsys):
    # 设角色须走配置态:建草稿 -> 写角色 -> 保存重启。master=0。
    with FakeDS10() as dev:
        rc = ds10_config.main(["--port", dev.port, "--role", "master"])

    assert rc == 0
    assert dev.seen == ["AT", "AT+CFG_NEW", "AT+CFG_ROLE=0", "AT+CFG_SAVE"]


def test_role_slave_writes_role_1(capsys):
    with FakeDS10() as dev:
        rc = ds10_config.main(["--port", dev.port, "--role", "slave"])

    assert rc == 0
    assert "AT+CFG_ROLE=1" in dev.seen


def test_role_save_failure_aborts_nonzero(capsys):
    # 保存校验失败须以非零退出,不能吞掉 +DS10ERR。
    with FakeDS10(error_on={"AT+CFG_SAVE": ("5", "DRAFT_VALIDATION_FAILED")}) as dev:
        rc = ds10_config.main(["--port", dev.port, "--role", "master"])

    assert rc != 0
    err = capsys.readouterr().err
    assert "DRAFT_VALIDATION_FAILED" in err or "DS10ERR" in err


def test_bind_enables_channel_then_sets_sn_and_saves(capsys):
    # 主机绑定从机 SN 到通道:建草稿 -> 启用通道 -> 写设备 ID -> 保存。
    # 文档要求写入非空设备 ID 前通道须已启用,故先 ,0,1 再 ,1,"SN"。
    with FakeDS10() as dev:
        rc = ds10_config.main(
            ["--port", dev.port, "--bind", "3", "DS1000000008"])

    assert rc == 0
    assert dev.seen == [
        "AT", "AT+CFG_NEW",
        "AT+CFG_CH=3,0,1",
        'AT+CFG_CH=3,1,"DS1000000008"',
        "AT+CFG_SAVE",
    ]


def test_bind_save_failure_aborts_nonzero(capsys):
    with FakeDS10(error_on={"AT+CFG_SAVE": ("5", "DRAFT_VALIDATION_FAILED")}) as dev:
        rc = ds10_config.main(
            ["--port", dev.port, "--bind", "3", "DS1000000008"])

    assert rc != 0
    err = capsys.readouterr().err
    assert "DRAFT_VALIDATION_FAILED" in err or "DS10ERR" in err
