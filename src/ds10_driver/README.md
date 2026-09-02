# ds10_driver

DS10 星闪 DTU 透传链路的 ROS 2 驱动（Modbus 模式）。打开一个串口，把应用层
`ds10_interfaces/Frame` 消息组成标准 Modbus RTU 帧写入串口，并把从串口字节流里解出的
完整帧还原成 `Frame` 发布出来。业务节点只需订阅/发布两个话题，无需关心串口、组帧、CRC
或帧定界。

## 角色

同一份驱动通过 `role` 参数区分主从：

- **master**：`~/tx` 的 `Frame.station_id` 作为目标从机站号组帧，DS10 按站号点对点路由；
  `~/rx` 的每条 `Frame` 带来源从机站号（1 主对最多 15 从的来源识别）。
- **slave**：`~/tx` 忽略 `station_id`，改用参数 `station_id` 组帧；`~/rx` 只发布发给本机
  站号的帧（DS10 已按通道路由，驱动再做一层过滤保险）。

## 接口

| 话题 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `~/tx` | `ds10_interfaces/Frame` | 应用 → 驱动 | 组 Modbus 帧写串口 |
| `~/rx` | `ds10_interfaces/Frame` | 驱动 → 应用 | 解出完整帧后发布 |
| `~/status` (diagnostics) | `diagnostic_msgs/DiagnosticArray` | 驱动 → 应用 | 连接状态、收发帧数、重同步丢字节数（链路噪声地板） |

## 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `port` | `/dev/ttyUSB0` | 串口设备 |
| `baud` | `115200` | 波特率（8N1） |
| `role` | `master` | `master` / `slave` |
| `station_id` | `0` | 从机必填 1–247；主机忽略 |
| `frame_timeout_ms` | `20` | reader 判定突发结束的静默间隔（实测标定） |
| `max_frame_bytes` | `4095` | 单帧上限，tx 超限拒绝（DS10 实测重组天花板 ≈4095B） |
| `tx_topic` / `rx_topic` | `~/tx` / `~/rx` | 可重映射，支持一机多实例 |

## 运行

```bash
# 主机侧
ros2 launch ds10_driver ds10_master.launch.py port:=/dev/ttyUSB0

# 从机侧（15 台分别配 station_id=1..15）
ros2 launch ds10_driver ds10_slave.launch.py port:=/dev/ttyUSB1 station_id:=1
```

## 帧定界

Modbus RTU 帧无长度字段，且 DS10 无线链路会粘包/拆包，故 reader 采用**混合定界法**
（静默间隔粗切突发 + CRC 试探细切帧）：从每个候选起点要求站号 ∈ [1,247]，递增候选长度
试 CRC-16/MODBUS，命中即认定一帧；配不出的字节逐字节滑过重同步，尾部半帧保留待拼接。
CRC 失败的字节段不产出 `Frame`（丢弃计入诊断的重同步丢字节数）。该策略在真实主/从链路
实测 100% 到达率。

## 测试

```bash
colcon test --packages-select ds10_driver
```

- `test_modbus_frame_codec`（gtest，seam 1）：CRC、组帧/解帧、粘包/半帧/噪声重同步/
  越界站号/空帧/近上限长帧/超限拒绝等纯逻辑用例。
- `test_ds10.launch.py`（launch_testing + PTY，seam 2）：真实节点 + 伪串口，验证
  `~/tx` → 组帧 → 串口 与 串口 → 解帧 → `~/rx` 全链路。
