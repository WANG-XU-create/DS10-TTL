# 03 — 配置主机(Modbus 模式 + 通道绑定 SN + 链路读回校验)

**What to build:** `--role master --bind <channel>,<slaveSN>[,<addr>]` 一条命令把一台 DS10 配成主机。脚本进入 AT 会话后下发 `CFG_NEW → CFG_ROLE=0 → CFG_WORK=1`(Modbus 模式)`→ CFG_UART=115200,8,0,1 → CFG_SLE=1,1 → CFG_CH`(启用通道 / 绑定从机 SN / 设 Modbus 地址)`→ CFG_SAVE`。发送任何帧之前先校验 SN 格式(12 字符、`DS` 前缀、通过 Luhn)。复用 ticket 02 的保存 / 重启 / 重连机制,读回角色、工作模式、通道绑定**与链路状态**并比对,打印"✅ 配置已生效"或列出不符项。

链路状态读回在此身兼两职:既确认主机与所绑定从机建立了链路,又是对"主从 SLE 预设是否必须一致才能建链"这一文档空白的唯一实测检验。

**Blocked by:** 02 — 配置从机(含 CFG_SAVE 保存 / 重启 / 重连 / 读回校验)

**Status:** ready-for-agent

- [ ] `--role master --bind <channel>,<slaveSN>[,<addr>]` 解析通道、从机 SN 与可选 Modbus 地址
- [ ] 发出任何帧之前校验从机 SN 格式(12 字符、`DS` 前缀、Luhn 校验);非法 SN 立即拒绝并非零退出
- [ ] 下发主机配置序列:`CFG_NEW → CFG_ROLE=0 → CFG_WORK=1 → CFG_UART=115200,8,0,1 → CFG_SLE=1,1 → CFG_CH`(通道启用 / 属性 1 设 SN / 属性 2 设 Modbus 地址)`→ CFG_SAVE`
- [ ] 无线 SLE 预设与从机一致:显式设为 Polar 码 + 均衡档(frameType=1, tier=1)
- [ ] 复用 ticket 02 的保存 / 重启 / 重连机制
- [ ] 读回角色、工作模式、通道绑定与链路状态,与期望值比对
- [ ] 全部相符(含链路已建立)打印"✅ 配置已生效";否则列出所有不符项并非零退出
- [ ] 测试:主机正常路径(发出正确 AT 顺序含 `CFG_WORK=1` 与 `CFG_CH` 绑定、模拟重启后重连、读回相符且链路建立 → 退出 0);非法 SN 在发帧前被拒;读回 / 链路不符被报告并非零退出
