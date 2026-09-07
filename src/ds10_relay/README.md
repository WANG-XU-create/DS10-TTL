# ds10_relay

DS10 透传链路上的**三跳请求/应答中继**：主机发数据给从机1 → 从机1 回复并**指定这份回复
该转发给谁** → 主机按从机指定的目标转发。建立在 `ds10_driver` 的话题之上，不碰串口、
不改链路帧格式。

## 路由权在从机（本包的核心设计）

转发目标**不由主机配置**，而是从机在回复里携带的 `dst` 字节。主机只做合法性校验
（`dst ∈ [1,247]` 且不等于来源站号），**不覆盖**从机的决定。

这带来三个实际差别：

- 从机可以**按载荷内容**把不同数据派往不同目标（温度给站2、湿度给站3）；
- 从机可以**拒绝转发**：`dst=0` 表示「回复我但别转发」；
- **新增目标站号只需改从机的路由表**，主机无需改配置或重启。

## 角色

同一个可执行文件通过 `role` 参数区分两端（与 `ds10_driver` 的 `master`/`slave` 同构）：

- **relay**（主机侧）：发请求给从机1 → 按事务号匹配回复 → 读出 `dst` → 把业务载荷转发给
  `dst` 指定的从机。超时自动重试。主机自己不持有任何转发目标。
- **responder**（从机侧）：收到请求 → 用 `route_map` 按载荷内容选 `dst` → 回复。

```
        ┌──────────────── relay (主机侧) ────────────────┐
[1] 请求 │  /master/tx  station=slave1                   │
        │  F1 F1 <txn> <payload>                        │
        └───────────────────────┬───────────────────────┘
                                ▼  DS10 无线
        ┌────────────── responder (从机1 侧) ────────────┐
[2] 应答 │  按 route_map 匹配载荷 → 选出 dst              │
        │  /slave1/tx: F1 F2 <txn> <dst> <payload>      │
        └───────────────────────┬───────────────────────┘
                                ▼
[3] 转发 │  /master/rx (station=slave1, txn 匹配) → 读 dst
        │  → /master/tx (station=dst) → 目标从机
        │  dst=0 则不转发
```

## 接口

| 话题 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `tx_topic` | `ds10_interfaces/Frame` | 中继 → 驱动 | 请求与转发都走这里 |
| `rx_topic` | `ds10_interfaces/Frame` | 驱动 → 中继 | 回复入口 |
| `~/trigger` | `std_msgs/String` | 外部 → 中继 | 发起一次事务，`data` 即载荷（仅 relay 角色） |
| `~/stats` | `std_msgs/String` | 中继 → 外部 | 计数快照，默认每 5s |

## 参数

| 参数 | 默认 | 角色 | 说明 |
|------|------|------|------|
| `role` | `relay` | both | `relay` / `responder` |
| `slave1_id` | 1 | relay | 被请求的从机站号（1–247） |
| `route_map` | `""` | responder | `"keyword:station,..."`，按载荷内容选目标，首个命中者胜 |
| `default_dst` | 0 | responder | 无关键字命中时的目标；0=回复但不转发 |
| `function_code` | `0x10` | relay | 组请求帧用的 Modbus 功能码 |
| `timeout_ms` | 1500 | relay | 单次尝试等回复的超时（实测标定，见下） |
| `max_retries` | 2 | relay | 超时后重试次数，0=不重试 |
| `auto_interval_ms` | 0 | relay | >0 时每 N ms 自动发起一次（压测用） |
| `auto_payload` | `ds10_relay auto probe` | relay | 自动模式的载荷 |
| `stats_interval_ms` | 5000 | both | `~/stats` 发布周期，0=关闭 |
| `tx_topic` / `rx_topic` | `/master/tx` `/master/rx` | both | 绝对话题名，对齐 `start_ds10.sh` |
| `trigger_topic` | `~/trigger` | relay | 触发入口 |

**注意 `route_map` 的顺序有意义**：首个命中的关键字胜，所以更具体的关键字要放前面
（`"temp:2,temperature:3"` 里 `temperature=20` 会被 `temp` 先吃掉，应写成
`"temperature:3,temp:2"`）。关键字按 UTF-8 字节匹配，中文可直接用：`"温度:2,湿度:3"`。
格式错误或站号越界会在**启动时抛错退出**，不会静默不路由。

## 运行

有两种玩法，**自动栈**（应答器按 `route_map` 自动决定 dst）和**交互式手动测试**
（你手动打回复并选 dst）。**两者不能同时跑**——都跑会一个请求两份回复。

### A. 全自动栈（一键脚本）

```bash
# 终端1: 一键起 3 驱动 + 从机1 自动应答器 + 主机中继
./start_relay.sh
#   自定义路由:  ROUTE_MAP="temp:2,humid:2" ./start_relay.sh
#   无命中也转:  DEFAULT_DST=2 ./start_relay.sh

# 终端2: 触发一次事务, 应答器按内容自动选 dst
ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'temp=25.3'}"
ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'other'}"   # 不命中 -> 不转发

# 看结果
ros2 topic echo /ds10_relay/stats     # 中继计数
ros2 topic echo /slave2/rx            # 转发目标实收
```

### B. 交互式手动测试（人在环，你打回复）

主机端你敲请求，从机1 端你敲回复并选转发目标——完整体验「从机按内容决定转给谁」。
**注意用 `start_ds10.sh`（只起驱动），不要用 `start_relay.sh`**（自动应答器会抢答）。

```bash
# 终端1: 只起驱动
./start_ds10.sh

# 终端2: 主机 —— 你敲请求。超时放长、关重试, 给你留打字时间
python3 test/ds10_relay_master.py --timeout 60 --retries 0

# 终端3: 从机1 —— 收到请求后你敲回复内容和目标站号 dst
python3 test/ds10_relay_responder_interactive.py --default-dst 2
```

一次事务的样子：终端2 敲 `temp=25.3` 回车 → 终端3 显示 `<< 收到请求 ... 'temp=25.3'`，
提示你输入回复内容（回车=原样回显）和 dst（回车=默认 2）→ 终端2 收到回复并转发给 dst
指定的从机。

### C. 端到端耗时测试（自动，固定内容）

测三跳往返总耗时。三台 DS10 挂同一台 Jetson，脚本在一个进程内同时扮演主机、从机1
应答、计时三个角色——但每一跳仍真实过无线（经各自的驱动），所以测的是真实往返。
**同样只用 `start_ds10.sh`**，不要跑 A 的自动栈（会抢角色，脚本会告警）。

```bash
./start_ds10.sh                                   # 终端1: 只起驱动
python3 test/ds10_relay_timing.py                 # 终端2: 跑一次
python3 test/ds10_relay_timing.py --count 20      # 跑 20 次出统计
```

固定内容：主机发 `上海赛索德智能科技有限公司位于上海市虹口`，从机1 回
`好的，已收到贵公司准确地址上海虹口区四川北路` 并要求转发给站号2。输出把总耗时拆成
5 段（下行 / 从机1 处理 / 上行 / 主机转发处理 / 转发下行），并给出「从机2 收到」的总耗时。
某跳丢失时会报「最远到达阶段」而非挂死。

### 手动逐节点（等价于 A，用于调参）

```bash
./start_ds10.sh
ros2 launch ds10_relay ds10_responder.launch.py route_map:="temp:2,humid:3"
ros2 launch ds10_relay ds10_relay.launch.py
ros2 topic pub --once /ds10_relay/trigger std_msgs/String "{data: 'temp=25'}"
```

链路远/慢时放宽超时：`ros2 launch ds10_relay ds10_relay.launch.py timeout_ms:=2000`


## 事务头

`data` 开头 4 字节承载事务号：

```
请求  F1 F1 <txn_hi> <txn_lo> <payload...>
      └──┬──┘ └──────┬──────┘
       魔数      事务号(大端)

回复  F1 F2 <txn_hi> <txn_lo> <dst> <payload...>
      └──┬──┘ └──────┬──────┘ └─┬─┘
      回复魔数    事务号        从机指定的转发目标
                              0 = 不转发
```

**为什么回复用不同魔数（`F1 F2`）—— 这是必要的，不是美观问题。** 请求与回复的长度是
重叠的，单靠长度无法区分。若两者共用 `F1 F1`，那么一个 4B 头的旧格式回复，其**载荷首
字节会被误读成 `dst`**。而可见 ASCII（32–126）**全部落在合法站号范围（1–247）内**：

| 旧格式回复载荷 | 会被误转发到 |
|---|---|
| `"Hello"` | 站号 72 |
| `"temp=25"` | 站号 116 |

站号「合法」，所以 `bad_dst` 校验拦不住 —— 数据会被**静默投递到错误的从机**，比直接丢弃
更糟。用不同魔数让格式自描述后，旧格式回复会被识别为格式不符、计入 `bad_dst` 并告警。
gtest 里 `RequestFormatNeverYieldsDst` 就是守这条的。

**为什么塞在 `data` 里而不加消息字段**：`ds10_driver` 组帧时只用
`station_id / function_code / data`（见 `ds10_node.cpp` 的 `on_tx`），`Frame.tx_seq`
**不会上无线**，所以请求/回复配对必须靠 `data` 内的序号。选 `0xF1` 开头 + 大端布局是为了与
`DS10_Modbus/test/` 下的 pyserial 工具**线上格式一致**，C++ 节点与 Python 脚本可以互通
（已实测双向验证，见下）。反之若改宽链路帧，会让 11 个裸串口脚本全部失效，也会重新引入
`.scratch/ds10-modbus-driver/spec.md:74` 明确否决过的「在 Modbus 帧上再套一层应用帧」。

代价：请求头占 4B、回复头占 5B。有效载荷上限分别是 **4087B**（`kMaxPayload`）与
**4086B**（`kMaxReplyPayload`）。超限在中继侧就拒绝并计入 `oversized`，不等驱动报
`tx_rejected`。

**转发时不带事务头**：`txn` 与 `dst` 是主机↔从机1 的记账，对目标从机无意义，故只转发
业务载荷本身。

## 丢弃策略（重要）

不匹配的帧一律**计数但只在 DEBUG 级打印**：

- 来源站号不是 `slave1_id`
- 没有事务头
- 空闲时收到帧（超时后迟到的回复）
- 事务号与当前 pending 不符（重复回复的第 2..N 份）

这些在无线链路上都是**正常现象**（重传、迟到），用 INFO/WARN 会在链路一有重复时刷屏、
把真正的失败信息淹掉。但**绝不静默**：全部累计到 `~/stats` 的 `ignored`。如果这个数远
大于 `sent`，说明有重复应答器、无线重传严重、或 `timeout_ms` 标定过紧。

以下情况级别更高（WARN），因为它们不是正常现象而是配置/版本问题，计入 `bad_dst`：

- 回复不是回复格式（缺 `F1 F2` + `dst`）→ 对端版本不匹配
- `dst` 超出 1–247
- `dst` 等于来源站号（会造成回环，中继自己追自己）

`~/stats` 字段：`sent ok failed retried timeouts forwarded no_forward bad_dst
oversized ignored`。`no_forward` 是从机主动要求不转发的次数（正常业务），与
`bad_dst`（异常）分开计数。

看丢弃原因：`--ros-args --log-level debug`

## 实机标定（2026-09-04，真实 DS10 电台，桌面近距离）

三台 DS10 挂同一台 Jetson（ttyUSB0/1/2），`resync_dropped_bytes=0`（链路字节级干净）。

**RTT 随载荷急剧增长**，`timeout_ms` 必须按业务载荷选：

| 载荷 | RTT p50 | RTT p90 | RTT max | 样本 |
|---|---|---|---|---|
| 30B | 30 ms | 31 ms | 53 ms | 43 |
| 504B | 247 ms | 253 ms | 265 ms | 84 |
| 1004B | 602 ms | 717 ms | 764 ms | 59 |

默认 `timeout_ms=1500` 覆盖实测最坏 764ms 并留 ~2x 余量。若业务载荷只有几十字节，
可收紧到 200–300ms 以更快发现丢帧。

**丢帧率**：30B 载荷 84 次事务中 1 次三连超时放弃（整帧无线丢失，非字节损坏，因为
`resync_dropped_bytes` 恒为 0）；重试挽回了另外 2 次。**这正是 `max_retries` 存在的理由** ——
关掉重试会把这类偶发丢帧直接暴露成业务失败。

### ⚠ 上行存在 ~1100B 天花板（链路不对称，与本包无关）

实测边界很陡：

| 方向 | 实测可达 |
|---|---|
| 下行 主机→从机 | **4008B 整帧 OK** |
| 上行 从机→主机 | **1008B OK，1108B 起 100% 失败** |

已用「从机主动上行、完全绕开 responder」的方式独立复现，故**这是电台/配置层面的上行限制，
不是 `ds10_relay` 或 `ds10_driver` 的缺陷**。应答器原样带回载荷，回复比请求还多 1B（`dst`），
所以**请求载荷超过约 1000B 就永远等不到回复**（表现为三连超时放弃）。

影响与规避：
- 业务载荷请控制在 **1000B 以内**；
- 需要更大上行时，先查 DS10 配置小程序的 SLE 档位/功率/可靠广播设置，或改用下行大包 +
  上行小包确认的模式；
- 此上限与 `spec.md` 记录的「1501–4096B 由 DS10 自动分包重组」不一致，怀疑与当前
  SLE 档位或上行调度有关，**换配置/固件后需复测**。

## 测试

```bash
colcon test --packages-select ds10_relay
```

`test_transaction.cpp`（gtest，seam 1）27 个用例，两组：

**事务头编解码**：请求/回复字节布局、txn 全范围往返（含 0/0xFFFF 边界）、残缺头与错魔数
拒绝、无头数据原样返回、请求与回复格式互斥、`dst=0` 与站号范围校验、两种载荷上限边界，
以及一条 **Python 实测抓包帧**的字节级比对。其中 `RequestFormatNeverYieldsDst` 是防静默
误路由的守卫——它断言一个 `F1 F1` 帧即使第 5 字节是合法站号（如 `'H'`=72）也绝不产出
`dst`。

**路由表**（`route_map`）：解析正常项、容忍空白与尾逗号、关键字含冒号、非法项抛错
（缺站号/非整数/站号越界）、子串匹配、首个命中者胜、UTF-8 中文关键字、无命中回落默认、
二进制载荷不误匹配。

状态机本身不做单测（`RelayNode` 内部方法是实现细节），改用与 Python 脚本交叉验证。
`ds10_relay_responder.py` 与 `ds10_relay_master.py` 已同步到新协议，并验证过与 C++
**字节级一致**（回复帧 `f1 f2 01 02 07 68 69` 与 gtest 断言逐字节相同，路由表行为亦一致）。
