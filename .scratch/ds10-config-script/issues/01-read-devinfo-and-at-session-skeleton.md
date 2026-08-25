# 01 — 读取 DS10 设备信息(SN)+ AT 会话与假 DS10 测试骨架

**What to build:** 一条最薄的完整贯穿路径。CLI 通过 `by-id` 路径打开串口,用 `+++` 然后 `AT` 进入 AT 会话,发出设备信息查询,解析并打印型号 / SN / 版本 / maxSlaves,然后以状态相符的退出码结束。同时建立"假 DS10 over PTY"的测试骨架,后续两票复用。用户运行这一票就能读出一台 DS10 的 SN,供 ticket 03 的 `--bind` 参数使用。

这一票把最容易出错的底层地基先打通并可测:`by-id` 串口打开、PTY 测试夹具、进入 AT、`+DS10ERR` 处理、退出码约定。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] 单文件 Python + pyserial 脚本落在 `DS10_Modbus/` 根目录,与现有两个脚本风格一致(argparse `parse_args`、返回退出码的 `main()`、中文帮助与提示、`dump()` 风格收发帧打印),零新依赖
- [ ] 接受 `by-id` 串口路径参数;打开失败时给出清晰的中文报错与非零退出码
- [ ] 能用 `+++` 然后 `AT` 进入 AT 会话,并读回显示设备响应
- [ ] 发出设备信息查询,解析出型号 / SN / 版本 / maxSlaves 并打印
- [ ] 收到 `+DS10ERR` 时停止,报出错误码与原因,并以对应非零退出码退出
- [ ] 验证成功退出码为 0;打开/连接失败与 `+DS10ERR` 使用各自不同的非零退出码
- [ ] 建立假 DS10 over PTY 的 pytest 测试夹具:假的一侧持有 PTY 的 master 端,把对端打开期间的瞬态 `EIO`/`EAGAIN` 视为非致命并轮询而非退出(复用 `modbus_rtu_bus_driver` 的 PTY 先例)
- [ ] 测试:端到端驱动 CLI 读取设备信息,断言发出的 AT 帧顺序与内容,并断言在假 DS10 返回 `+DS10ERR` 时正确中止
