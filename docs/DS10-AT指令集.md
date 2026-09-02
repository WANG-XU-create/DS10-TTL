# DS10 软调试 AT 指令集 (V1.0.0)

> 适用硬件：DS10-TTL / DS10-R232 / DS10-R485
> 固件版本：V1.0.0　发布：2026 年 8 月
> 本文由官方 PDF 转换整理，已去除页眉页脚。命令集覆盖角色、SLE 无线参数、业务模式、通道配置、硬件设置与运行诊断。

在线配置/AT 翻译器：https://app.bearpi.cn/pwm/ds10/?fw=1.0.0 （网页仅生成命令，不会自动写入设备）。

---

## 1. 使用前说明

### 1.1 进入 AT 前的先决条件

必须先在**小程序（蓝牙）或上位机（串口）的硬件配置**中，将 **“AT 指令配置通道”设为启动**并保存/下发。未启动该通道时，设备无法进入或使用 AT 会话。

进入步骤：

1. 设备开关拨到 **DEBUG** 模式。
2. 通过小程序或上位机连接设备。
3. 在硬件配置中启动“AT 指令配置通道”，并下发配置。
4. 设备开关拨回 **RUN** 模式；随后通过串口发送触发串（默认 `+++`）进入 AT 模式。

---

## 2. AT 使用总览

### 2.1 两种 AT 平面

| 平面 | 进入方式 | 适用操作 |
|---|---|---|
| 运行态 AT | 进入 AT 会话后的默认平面 | 查询设备与链路状态、不写 Flash 的即时控制；不修改配置草稿 |
| 配置态 AT | 在运行态执行 `AT+CFG_NEW` 后进入 | 修改角色、无线、业务、通道和硬件配置；命令操作 RAM 草稿，保存并重启后生效 |

平面切换与草稿处理：

- 进入运行态：`+++` → `AT` → 运行态 AT
- 进入配置态：`AT+CFG_NEW` → 配置态 AT
- 结束配置：`AT+CFG_SAVE`（保存并重启） / `AT+CFG_DISCARD`（放弃草稿）

配置态命令默认操作 RAM 草稿，不会立即改变正在运行的配置。除草稿创建和状态查询等例外命令外，配置命令要求草稿已存在，否则返回 `+DS10ERR:2,CFG_NOT_LOADED`。

### 2.2 推荐操作流程（首次配置 / 现场调试）

| 步骤 | 目的 | 命令 |
|---|---|---|
| 01 进入 AT 会话 | 从 RUN 透传进入调试会话并确认串口 | `+++` · `AT` |
| 02 确认设备能力 | 读取型号、版本、能力列表 | `AT+DEVINFO?` · `AT+CAP?` |
| 03 创建配置草稿 | 建默认草稿并加载当前硬件配置 | `AT+CFG_NEW` |
| 04 加载现有配置（可选） | 仅改一部分时加载现配置 | `AT+CFG_LOAD` |
| 05 设置角色与无线 | 主从角色 + SLE 预设/专家参数 | `AT+CFG_ROLE=<role>` · `AT+CFG_SLE=<frameType>,<tier>` · `AT+CFG_SLEC=...` |
| 06 设置业务模式 | 广播/Modbus/规则路由 | `AT+CFG_WORK=<mode>` · `AT+CFG_BCAST=<type>` · `AT+CFG_NTP=...` |
| 07 配置从机通道 | 启用通道、设 SN/Modbus ID/路由 | `AT+CFG_CH=<channel>,...` · `AT+CFG_GETCH=<channel>` |
| 08 配置本机硬件 | RUN UART、发射功率、STATUS 用途 | `AT+CFG_UART=...` · `AT+CFG_POWER=<level>` · `AT+CFG_STATUS=...` |
| 09 检查草稿 | 保存前检查草稿与摘要 | `AT+CFG_STATE?` · `AT+CFG_SHOW?` |
| 10 保存并重启生效 | 全量校验后原子保存并重启 | `AT+CFG_SAVE` |
| 11 重进并诊断 | 确认运行状态与 SLE 链路 | `AT+STATE?` · `AT+LINK?` · `AT+GETLINK=<channel>` |
| 12 结束 AT 会话 | 退出 AT，恢复 RUN 透传 | `AT+ENTM` · `AT+CFG_DISCARD` |

> 注意：草稿已修改时不能直接执行 `AT+ENTM`；须先 `AT+CFG_SAVE` 保存，或 `AT+CFG_DISCARD` 放弃。

### 2.3 输入与响应规则

- 命令形式：`AT+<FUNCTION>?` 查询当前值；`AT+<FUNCTION>=?` 查询支持范围；`AT+<FUNCTION>=<参数>` 设置/执行；`AT+<FUNCTION>` 无参数控制。
- 命令以\r\n结束,参数以逗号分隔；字符串参数可用双引号包裹；HEX 参数仅允许 `0-9 A-F`，且必须为偶数个字符。
- 成功响应以 `OK` 结束；失败响应为 `+DS10ERR:<code>,<reason>` 后接 `ERROR`。上位机应以终止行判断命令完成。

---

## 3. AT 命令标准参考

命令按执行平面分为**共用 AT**、**运行态 AT** 和**配置态 AT**。

### 3.1 共用 AT

进入 AT 会话后即可用，不依赖当前平面。

#### AT — 检查 AT 会话是否正常
- 格式：`AT`（无参数）
- 成功：`OK`

#### AT+ENTM — 退出 AT 会话并恢复 RUN 数据透传
- 格式：`AT+ENTM`（无参数，草稿未修改时可退出）
- 成功：`OK`；未保存草稿时：`+DS10ERR:5,UNSAVED_DRAFT`

#### AT+CAP — 读取当前固件支持的私有能力列表
- 格式：`AT+CAP?`（运行 AT 与配置 AT 均可用）
- 成功：`+CAP:<capability-list>` + `OK`

#### AT+DEVINFO — 读取型号、SN、软件版本和最大从机数
- 格式：`AT+DEVINFO?`
- 成功：`+DEVINFO:<model>,<sn>,<version>,<maxSlaves>` + `OK`
- 说明：`maxSlaves` 即通道数上限，配置通道时以此为准。

### 3.2 运行态 AT

进入 AT 后的默认平面，仅查询状态/链路/GPIO，不修改草稿或持久化。

#### AT+STATE — 查询 RUN 状态、当前角色和工作模式
- 格式：`AT+STATE?`（草稿存在时也可查询）
- 成功：`+STATE:<runState>,<role>,<workMode>` + `OK`
- 取值：`runState` 0 非 RUN / 1 RUN；`role` 0 主机 / 1 从机；`workMode` 0 广播 / 1 Modbus / 2 自定义路由。

#### AT+LINK — 查询所有当前 SLE 链路状态
- 格式：`AT+LINK?`（主机逐通道返回，从机返回 channel 0）
- 成功：逐行 `+LINK:<channel>,<state>,<peer>,<rssi>`，最后 `OK`
- `state`：0 断开 / 1 配置中 / 2 IOB 待就绪 / 3 就绪 / 4 失败（仅主机）
- `peer`：主机侧为从机 SN，从机侧为主机 MAC；`rssi=127` 表示尚未取得有效 RSSI

#### AT+GETLINK — 查询指定通道的当前链路
- 格式：`AT+GETLINK=<channel>`（从机仅允许 `channel=0`）
- 成功：`+LINK:<channel>,<state>,<peer>,<rssi>` + `OK`（state/peer/rssi 含义同上）

#### AT+GPIO — 查询 STATUS 引脚用途/电平，或即时控制开漏输出
- 格式：`AT+GPIO?` 查询；`AT+GPIO=<0|1>` 设置
- 约束：设置仅在**已生效 `CFG_STATUS=1` 且没有配置草稿**时允许；不写 Flash
- 成功：查询 `+GPIO:<function>,<level>` + `OK`；设置 `OK`

### 3.3 配置态 AT

配置态命令默认操作 RAM 草稿；除草稿创建与状态查询等例外命令外，须先 `AT+CFG_NEW`。失败统一返回 `+DS10ERR:<code>,<reason>` + `ERROR`。设置类命令成功通常返回 `+CFG_DRAFT:1` + `OK`（表示已写入草稿，保存后生效）。

#### 草稿会话管理

**AT+CFG_NEW** — 创建默认业务配置草稿（保留当前主从角色并加载当前硬件配置），进入配置 AT
- 格式：`AT+CFG_NEW`（草稿已修改时不可覆盖）
- 成功：`+CFG_NEW` + `+CFG_STATE:1,0` + `OK`
- 说明：业务配置用产品默认值；主从角色、硬件配置、AT 调试开关和触发串保留设备当前值。

**AT+CFG_LOAD** — 将当前有效配置完整加载到已创建的草稿
- 格式：`AT+CFG_LOAD`（必须先 `AT+CFG_NEW`）
- 成功：`+CFG_LOAD` + `+CFG_STATE:1,0` + `OK`

**AT+CFG_STATE** — 查询草稿是否存在及是否修改
- 格式：`AT+CFG_STATE?`
- 成功：`+CFG_STATE:<draftExists>,<modified>` + `OK`

**AT+CFG_SAVE** — 完整校验并原子保存草稿，随后重启生效
- 格式：`AT+CFG_SAVE`（草稿必须满足组合与业务规则）
- 成功：`+CFG_SAVE:REBOOTING` + `OK`；校验失败时保留原配置

**AT+CFG_DISCARD** — 丢弃 RAM 草稿并回到运行态
- 格式：`AT+CFG_DISCARD`（不写 Flash）
- 成功：`+CFG_DISCARD:OK` + `OK`

**AT+CFG_SHOW** — 输出草稿的角色、工作模式、SLE、通道与硬件摘要
- 格式：`AT+CFG_SHOW?`（要求草稿已存在）
- 成功：多行 `+CFG_SHOW:ROLE,<role>` / `+CFG_SHOW:WORK,<workMode>` / `+CFG_SLE:...` / `+CFG_RATE:...` / `+CFG_SHOW:CHANNELS,<enabledChannels>,<maxSlaves>` / `+CFG_SHOW:HARDWARE,<baud>,<powerLevel>,<statusFunction>`，最后 `OK`

#### AT+CFG_ROLE — 主从角色

- 格式：`AT+CFG_ROLE?` / `AT+CFG_ROLE=?` / `AT+CFG_ROLE=<role>`
- 参数：`role` 0 主机 / 1 从机。设置后须 `AT+CFG_SAVE`，重启后生效
- 成功：查询 `+CFG_ROLE:<role>`；范围 `+CFG_ROLE:(0,1)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_SLE — 无线预设档位

- 格式：`AT+CFG_SLE?` / `AT+CFG_SLE=?` / `AT+CFG_SLE=<frameType>,<tier>`
- 参数：
  - `frameType`：0 GFSK / 1 Polar 码
  - `tier`：0 距离优先 / 1 均衡 / 2 速率传输。设置后同步更新帧类型、PHY、导频和 MCS，但不修改草稿中已有的 `timeout`（`CFG_NEW` 默认 timeout=0；`CFG_LOAD` 后设预设保留原 timeout）
- 成功：查询 `+CFG_SLE:<frameType>,<tier>,<phyRate>,<pilotDensity>,<mcs>,<timeout>` + `+CFG_RATE:<codedKbps>,<pilotAdjustedKbps>`（用专家配置且参数不匹配任一预设时 `tier=255`）；范围 `+CFG_SLE:(0,1),(0-2)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_SLEC — 专家级 PHY / 导频 / MCS / 超时

- 格式：`AT+CFG_SLEC=?` / `AT+CFG_SLEC=<frameType>,<phyRate>,<pilotDensity>,<mcs>[,<timeout>]`
- 参数：
  - `frameType`：0 GFSK / 1 Polar 码
  - `phyRate`：0 1M / 1 2M / 2 4M（4M 仅用于 ACB；启用 IOB 时 IOB PHY 自动用 2M）
  - `pilotDensity`：0 4:1 / 1 8:1 / 2 16:1（仅 Polar 保留；GFSK 下自动归零）
  - `mcs`：Polar 为 5/6/7/9/10/11（GFSK 下自动归零）
  - `timeout`：省略或 0 自动计算；`10..3200`（单位 10ms，对应 100ms..32s）
- 说明：专家命令不提供 `?` 查询，写入后通过 `AT+CFG_SLE?` 读实际参数
- 成功：范围 `+CFG_SLEC:(0,1),(0-2),(0-2),(0-11),(0,10-3200)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_WORK — 全局业务模式

- 格式：`AT+CFG_WORK?` / `AT+CFG_WORK=?` / `AT+CFG_WORK=<mode>`
- 参数：`mode` 0 广播 / 1 Modbus / 2 规则路由。切换会清理不适用的通道属性
- 成功：查询 `+CFG_WORK:<mode>`；范围 `+CFG_WORK:(0-2)`；设置 `+CFG_DRAFT:1,RESET:<count>`（RESET 始终返回，表示被清理的通道属性数量，未清理时为 `RESET:0`）

#### AT+CFG_BCAST — 广播类型

- 格式：`AT+CFG_BCAST?` / `AT+CFG_BCAST=?` / `AT+CFG_BCAST=<type>`
- 参数：`type` 1 纯可靠 / 2 纯 IOB / 3 智能混合
- 约束：仅在 `CFG_WORK=0`（广播）时可设置；NTP 已开启时不能直接切换为 1 纯可靠
- 成功：查询 `+CFG_BCAST:<type>`；范围 `+CFG_BCAST:(1-3)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_BCASTM — 智能混合广播的匹配规则

- 格式：`AT+CFG_BCASTM?` / `AT+CFG_BCASTM=<sendMode>,<matchHex>,<stripRoute>`
- 参数：
  - `sendMode`：1 可靠 / 2 IOB（匹配后采用该发送方式）
  - `matchHex`：`0-9 A-F` 连续字符串，长度 2–32 字符（对应 1–16 B），不带 0x/空格/分隔符；不得与 NTP 匹配头相同或互为前缀。示例 `A1B2`
  - `stripRoute`：0 保留路由头 / 1 剥离路由头
- 约束：设置时要求 `CFG_WORK=0` 且 `CFG_BCAST=3`（智能混合）
- 成功：查询 `+CFG_BCASTM:<sendMode>,<matchHex>,<stripRoute>`；设置 `+CFG_DRAFT:1`

#### AT+CFG_NTP — NTP 授时识别规则

- 格式：`AT+CFG_NTP?` / `AT+CFG_NTP=0` / `AT+CFG_NTP=1,<matchHex>,<stripRoute>`
- 参数：
  - `enable`：0 关闭 / 1 开启（开启须同时给 matchHex 和 stripRoute）
  - `matchHex`：`0-9 A-F` 连续字符串，长度 2–32 字符（对应 1–16 B）；不得与混合广播匹配头相同或互为前缀。示例 `1A2B`
  - `stripRoute`：0 保留 / 1 剥离路由头
- 约束：开启要求 `CFG_WORK=0` 且广播类型不是 `CFG_BCAST=1`（纯可靠）
- 成功：查询 `+CFG_NTP:<enable>[,<matchHex>,<stripRoute>]`；设置 `+CFG_DRAFT:1`

#### AT+CFG_CH — 从机逻辑通道、设备绑定及业务路由

**channel 是什么**：channel 是主机配置中的从机逻辑槽位，不是 UART 端口、SLE 频道或 Modbus 地址。每个启用的 channel 通过 SN 绑定一台目标从机；主机保存重启后，才会在 RUN 中按该绑定扫描、建链和转发数据。

**工作模式决定通道用到哪些属性**：

| 全局工作模式 | 通道配置 | 业务含义 |
|---|---|---|
| 广播 `CFG_WORK=0` | 属性 0 + 1 | 启用并绑定参与通信的从机；发送类型由 `CFG_BCAST` 系列决定 |
| Modbus `CFG_WORK=1` | 属性 0 + 1 + 2 | 主机读请求中的从站地址，把请求路由到配置了该地址的通道 |
| 自定义路由 `CFG_WORK=2` | 属性 0 + 1 + 3；属性 4 可选 | 主机按自定义内容匹配请求；从机回复可原样输出或加通道识别信息 |

**命令族总览**：

| 属性 | 用途 | 说明 |
|---|---|---|
| 查询 | 通道列表 | `AT+CFG_CH?` 查看全部通道启用与绑定摘要 |
| 查询 | 通道详情 | `AT+CFG_GETCH=<channel>` 查看单通道完整配置 |
| 0 | 通道启停 | 决定逻辑通道是否参与连接和业务转发 |
| 1 | 绑定从机 | 通过 SN 确定该通道对应的目标从机 |
| 2 | Modbus 地址路由 | 按从站地址或地址范围路由请求 |
| 3 | 自定义请求匹配 | 按数据内容决定请求发往哪个通道 |
| 4 | 从机回复封装 | 为返回数据添加文本或二进制识别头 |

统一命令格式：`AT+CFG_CH=<channel>,<property>,<arguments...>`。默认支持通道 1..15，实际上限以 `AT+DEVINFO?` 的 `maxSlaves` 为准。只改 RAM 草稿，`AT+CFG_SAVE` 后重启生效。

**推荐配置顺序**：① `CFG_NEW`（改现配置再 `CFG_LOAD`）→ ② 确认 `CFG_ROLE=0`，用 `CFG_WORK` 选模式 → ③ 属性 0 启用通道，属性 1 设 SN → ④ 广播无需额外规则、Modbus 配属性 2、自定义路由配属性 3（可选属性 4）→ ⑤ `CFG_GETCH` 检查后 `CFG_SAVE`。切换 `CFG_WORK` 时固件会清除不兼容的旧通道规则，并用 `RESET:` 返回清理数量。

**查询 · 通道列表** `AT+CFG_CH?`
- 成功：逐行 `+CFG_CH:<channel>,<enable>,<sn>,<name>,<workMode>`，最后 `OK`

**查询 · 完整配置** `AT+CFG_GETCH=<channel>`（channel=1..maxSlaves，仅返回当前工作模式允许的字段）
- 成功：`+CFG_CH:...`，再按模式附加 `+CFG_MODBUS:...` / `+CFG_MATCH:...` / `+CFG_WRAP:...`，最后 `OK`

**属性 0 · 通道启停** `AT+CFG_CH=<channel>,0,<0|1>`
- `0` 禁用 / `1` 启用。仅改启用状态，不自动清其他配置；主机模式下启用的通道保存时必须配有效 SN
- 成功：`+CFG_DRAFT:1` + `OK`

**属性 1 · 绑定从机** `AT+CFG_CH=<channel>,1,<sn>[,<name>]`
- `sn`：12 字符 DS10 SN，须以 `DS` 开头并通过 **Luhn 校验**；不同通道不得重复；留空同时清除 SN/名称/推导 MAC。若返回 `INVALID_DEVICE_ID`，请 `CFG_DISCARD` 后重建草稿，勿继续保存
- `name`：可选，最长 19 字节（中文按 UTF-8 占多字节），V1.0.0 名称不得含逗号；省略时保留原名称。写入非空 SN 前通道须已启用
- 成功：`+CFG_DRAFT:1` + `OK`

**属性 2 · Modbus 路由** `AT+CFG_CH=<channel>,2,<id-list>|0`
- `id-list`：单个地址或逗号分隔的地址/范围，如 `1,3-5,10-20`；`0` 表示清空
- 约束：仅 `CFG_WORK=1` 可用；地址 1..247，最多 8 段，不得重叠，范围起始不得大于结束
- 成功：`+CFG_DRAFT:1` + `OK`

**属性 3 · 自定义请求匹配**（仅 `CFG_WORK=2`）
- `AT+CFG_CH=<channel>,3,0,<matchHex>` 前缀匹配
- `AT+CFG_CH=<channel>,3,1,<offset>,<matchHex>` 固定偏移匹配（`offset` 0..1024）
- `AT+CFG_CH=<channel>,3,2,<matchHex>` 包含匹配
- `AT+CFG_CH=<channel>,3,3` 匹配全部数据（无需 offset/matchHex）
- `matchHex`：`0-9 A-F` 连续字符串，长度 2–64 字符（对应 1–32 B）。示例 `AA5501`
- 成功：`+CFG_DRAFT:1` + `OK`

**属性 4 · 从机回复封装**（仅 `CFG_WORK=2`）
- `AT+CFG_CH=<channel>,4,0` 不添加回复头
- `AT+CFG_CH=<channel>,4,1,<template>` 文本回复头（模板最长 63 字节，支持 `{channel}`、`{sn}`；含逗号须双引号）
- `AT+CFG_CH=<channel>,4,2,<syncHex>,<channelMode>,<lengthMode>` 二进制回复头
  - `syncHex`：1–16 B HEX；`channelMode` 0 不加 / 1 加 1 字节通道号；`lengthMode` 0 不加 / 1 两字节大端 / 2 两字节小端
- 成功：`+CFG_DRAFT:1` + `OK`

#### AT+CFG_UART — RUN UART 参数

- 格式：`AT+CFG_UART?` / `AT+CFG_UART=?` / `AT+CFG_UART=<baud>,<dataBits>,<parity>,<stopBits>`
- 参数：
  - `baud`：只能选下列值之一——1200 / 2400 / 4800 / 9600 / 14400 / 19200 / 38400 / 57600 / 115200 / 230400 / 460800 / 921600 / 1000000 / 1500000 / 2000000 / 3000000 / 4000000（不支持其他值）
  - `dataBits`：5..8
  - `parity`：0 None / 1 Odd / 2 Even
  - `stopBits`：1 / 2
- 成功：查询 `+CFG_UART:<baud>,<dataBits>,<parity>,<stopBits>`；范围 `+CFG_UART:(<baud-list>),(5-8),(0-2),(1,2)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_POWER — SLE 发射功率档位

- 格式：`AT+CFG_POWER?` / `AT+CFG_POWER=?` / `AT+CFG_POWER=<level>`
- 参数：`level` 0..7
- 成功：查询 `+CFG_POWER:<level>`；范围 `+CFG_POWER:(0-7)`；设置 `+CFG_DRAFT:1`

#### AT+CFG_STATUS — STATUS 引脚用途

- 格式：`AT+CFG_STATUS?` / `AT+CFG_STATUS=?` / `AT+CFG_STATUS=0` / `AT+CFG_STATUS=1,<onHex>,<offHex>`
- 参数：`function` 0 网络状态指示 / 1 开漏开关输出
  - `function=1` 时 `onHex`、`offHex` 必填，均为 1–16 B HEX 且不能相同
- 说明：设置后须保存并重启才生效
- 成功：查询 `+CFG_STATUS:<function>[,<onHex>,<offHex>]`；范围 `+CFG_STATUS:(0,1)`；设置 `+CFG_DRAFT:1`

---

## 4. 完整通道配置模板

基于当前有效配置修改通道 1。先选工作模式，再把 `<模式专用命令>` 替换为下表对应命令：

```
AT+CFG_NEW
AT+CFG_LOAD
AT+CFG_ROLE=0
AT+CFG_WORK=<mode>
AT+CFG_CH=1,0,1
AT+CFG_CH=1,1,<有效 DS10 设备 SN>,Sensor01
<模式专用命令>
AT+CFG_GETCH=1
AT+CFG_SAVE
```

| 模式 | 模式专用命令 | 说明 |
|---|---|---|
| 广播 | `AT+CFG_WORK=0` | 通道只需启用并绑定；发送类型另用 `CFG_BCAST` 配置 |
| Modbus | `AT+CFG_WORK=1`<br>`AT+CFG_CH=1,2,1-10` | 地址 1~10 的请求路由到通道 1 |
| 自定义 | `AT+CFG_WORK=2`<br>`AT+CFG_CH=1,3,0,AA55`<br>`AT+CFG_CH=1,4,0` | AA55 前缀路由到通道 1，回复原样输出 |

---

## 5. 错误响应

命令失败时先返回具体错误，再返回通用失败结果：

```
+DS10ERR:<code>,<reason>
ERROR
```

| code | 类别 | 常见 reason |
|---|---|---|
| 1 | 语法、命令形式或基本参数错误 | `SYNTAX_ERROR`、`READ_ONLY`、`LINE_TOO_LONG`、`INVALID_*` |
| 2 | 当前状态、工作模式或资源不允许 | `CFG_NOT_LOADED`、`WORK_MODE_NOT_ALLOWED`、`GPIO_NOT_SWITCH` |
| 3 | AT 命令队列已满 | `COMMAND_QUEUE_FULL` |
| 5 | 业务校验、草稿或配置组合冲突 | `UNSAVED_DRAFT`、`INVALID_DEVICE_ID`、`MATCH_PREFIX_CONFLICT`、`DRAFT_VALIDATION_FAILED` |
| 6 | 存储、运行时或底层操作失败 | `CONFIG_READ_FAILED`、`PERSIST_FAILED`、`LINK_SNAPSHOT_FAILED` |
| 7 | 当前固件不支持该命令 | `UNSUPPORTED_COMMAND` |

> `reason` 用于定位具体原因。同一 code 可对应多个 reason，上表为常见值，不限于表中项。

---

*源文档：DS10 软调试 AT 指令集 V1.0.0（PWM.cn，2026 年 8 月）。本 Markdown 已去除原 PDF 页眉页脚，供开发参考。*

