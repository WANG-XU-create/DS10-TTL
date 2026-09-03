# DS10 Application Protocol Specification v1

**Status**: Draft  
**Created**: 2026-09-02  
**Authors**: System Design Session  
**Supersedes**: None

---

## Problem Statement

DS10 驱动 (`ds10_driver`) 已经实现并验证通过,为上层提供了基于 Modbus RTU 帧骨架的透传能力(`Frame.msg`: station_id + function_code + data)。但驱动层只负责"串口 ↔ 帧骨架(CRC/去框)",不定义 `data` 字段的内部结构和语义。

上层业务节点(传感器上报、控制命令、日志推送等)需要一套**统一的应用层协议**来约束 `data` 字段的使用,实现以下目标:

1. **支持多种消息类型**(传感器数据、控制命令、日志、协议控制消息如 ACK)且可扩展
2. **支持文本和二进制数据**
3. **连续流消息的丢帧检测**(传感器/日志高频推送,需序号追踪)
4. **可选的可靠传输**(控制命令需确认送达)
5. **为未来扩展预留空间**(大文件分片传输、时间同步等)

当前业务节点直接操作 `Frame.data` 字节数组,每个应用自行定义格式,导致:
- 格式不统一,无法跨应用复用
- 缺乏丢帧检测机制
- 缺乏可靠性保证
- 扩展困难(如后续要加分片,每个应用都要改)

## Solution

在 DS10 驱动之上设计一套**应用层数据传输协议**,定义 `Frame.data` 字段的标准化布局、功能码语义、以及公共字段(flags/序号)。

协议以**独立上层节点/库**(`ds10_protocol` 包)的形式实现:
- 订阅 `ds10_driver` 的 `~/rx` 话题,解析 `Frame.data`,按协议规范提取 flags/序号/payload
- 发布 `~/tx` 话题,按协议规范封装应用 payload 为 `Frame.data`
- 处理协议层机制(ACK 自动回复、序号跟踪、错误检测)

业务应用可以:
- **第一版(MVP)**: 订阅 `/protocol/rx` / 发布 `/protocol/tx`(消息类型仍是 `Frame`,但 `data` 已按协议格式填充),自己解析 `data` 内部结构
- **第二版(生产)**: 订阅语义化话题(如 `/sensors/data` 发布 `SensorReading.msg`),协议节点做深度解析和分发

协议设计原则:
- **私有协议,仅借 Modbus RTU 帧骨架**—— 不追求与标准 Modbus 工具兼容(DS10 已透传、CRC 试探定长,本就偏离标准)
- **功能码驱动的消息分类**—— 用 8 位 `function_code` 区分消息大类,`data` 内部再细分
- **按需扩展**—— 第一版实现核心功能(控制命令+连续流),分片/时间同步等留到第二版
- **无版本协商**—— 靠功能码扩展实现演进,新功能占用新功能码,旧节点忽略未知功能码

---

## User Stories

### 协议设计与文档
1. As a 协议设计者, I want a 功能码分配表(0x00-0xFF 各段用途), so that 不同消息类型有清晰的命名空间且不冲突
2. As a 协议设计者, I want a 公共字段定义(flags/序号的含义和位置), so that 所有消息共享统一的元数据结构
3. As a 协议实现者, I want a Markdown 规范文档, so that 可以跨语言(C++/Python)实现该协议

### 消息类型支持
4. As a 传感器节点开发者, I want to 发送带序号的二进制传感器数据(功能码 0x10), so that 接收方能检测丢帧并解析 sensor_id + reading
5. As a 日志节点开发者, I want to 发送带序号的 UTF-8 文本日志(功能码 0x11), so that 日志流可追溯且支持中文
6. As a 控制节点开发者, I want to 发送不带序号的控制命令(功能码 0x12)并请求 ACK, so that 确认命令送达
7. As a 协议节点, I want to 收到请求 ACK 的消息后自动回复 ACK 帧(功能码 0x00), so that 发送方知道消息已送达

### 序号与丢帧检测
8. As a 接收方, I want to 每个连续流消息(0x10/0x11)带 uint16 序号, so that 能检测出序号跳变(丢帧)并日志警告
9. As a 接收方, I want to 序号按(station_id, 消息类型)独立编号, so that 一个从机的传感器丢帧不影响另一个从机的日志序号判断
10. As a 发送方, I want to 序号回绕时自动从 0 重新开始, so that uint16 空间用完后仍能继续工作

### 可靠性与错误处理
11. As a 发送方, I want to 在 flags 字段设置"请求 ACK"标志(bit0=1), so that 接收方知道需要确认
12. As a 接收方, I want to 收到格式非法的帧(未知功能码/data 长度不足)时日志警告但仍转发, so that 调试时不会出现"帧去哪了"的黑洞,且自行解析 data 的应用不被协议层截胡(见 §帧去留清单)
13. As a 接收方, I want to 检测到重复帧(相同序号)时丢弃不重复发布, so that 避免应用层把同一读数处理两次(第一版唯一的丢弃情形,见 §帧去留清单)
14. As a 运维人员, I want to 协议节点发布诊断话题(`/protocol/diagnostics`), so that 能监控未知功能码计数、丢帧计数、重复帧计数

### 扩展性
15. As a 协议设计者, I want to 功能码 0x80-0xFF 段预留给未来扩展, so that 后续加分片/时间同步等特性有命名空间
16. As a 协议设计者, I want to 定义分片帧格式(功能码 0x80, data=`[分片ID][总片数][当前片号][payload]`), so that 第二版可实现大文件传输
17. As a 协议实现者, I want to 第一版收到功能码 0x80 时日志警告"分片未实现"但仍转发, so that 为第二版铺路且不破坏当前系统(见 §帧去留清单)

### 部署与兼容
18. As a 运维人员, I want to 协议升级时新功能占用新功能码, so that 旧节点忽略未知功能码、新旧混跑不中断基础功能
19. As a 运维人员, I want to flags 保留位(bit2-7)发送时置 0, so that 第二版征用保留位时旧节点行为不受影响
20. As a 业务开发者, I want to 协议节点提供透明代理模式(订阅 `/protocol/rx`得到已封装的 Frame), so that 第一版快速验证、第二版再演进到语义化话题

---

## Implementation Decisions

### 协议归属层
- **独立上层节点/库**(`ds10_protocol` ROS 2 包),不修改 `ds10_driver`
- 驱动职责单一("串口 ↔ Modbus 帧骨架"),协议层负责"`data` 字段语义"
- 分层清晰:驱动→协议→业务,每层可独立演进和测试

### 功能码分配(Function Code Allocation)

8 位 `function_code` (0-255) 分三段:

| 范围 | 用途 | 第一版定义 |
|------|------|-----------|
| `0x00-0x0F` | **协议内部控制消息** | 0x00=ACK, 0x01=NACK(保留), 0x02=心跳(保留), 0x03=时间同步(保留), 0x0F=协议版本协商(保留) |
| `0x10-0x7F` | **应用数据消息** | 0x10=传感器上报, 0x11=日志, 0x12=控制命令, 0x13-0x7F=保留(按需扩展) |
| `0x80-0xFF` | **保留扩展特性** | 0x80=分片帧(第二版实现), 0x81-0xFF=保留 |

**设计原则**:
- 功能码表达"协议层 vs 应用层"和"控制 vs 数据"的大分类
- `data` 内部字段表达细节(如 0x10 的 data 首字节是 sensor_id)
- 新特性占用新功能码,已定义功能码的 `data` 布局不得改(向后兼容)

### 公共字段定义(Common Fields)

协议定义两个跨消息类型的公共字段,在 `Frame.data` 开头:

#### 1. **flags 字段**(1 字节,uint8)

| Bit | 含义 | 第一版行为 |
|-----|------|-----------|
| bit0 | **请求 ACK** (1=需要, 0=不需要) | 接收方检查,若=1 则自动回 0x00 ACK 帧 |
| bit1 | **分片标志** (保留,第二版可能征用) | 发送时置 0,接收时忽略 |
| bit2-7 | **保留** | 发送时必须置 0,接收时忽略 |

**用途**:
- 控制消息(0x12)通常 bit0=1(需确认)
- 连续流消息(0x10/0x11)通常 bit0=0(高频,不需每帧 ACK)
- 广播帧(若未来支持 station_id=255)即使 bit0=1 也不回 ACK(避免总线冲突)

#### 2. **seq 字段**(2 字节,uint16,小端序)

- **可选字段**:只有连续流消息(0x10/0x11)带序号,控制命令(0x12)不带
- 发送方递增(每发一帧 seq++),回绕时从 0 重新开始
- 接收方按 `(station_id, function_code, 流ID?)` 维护期望序号,检测跳变/重复
- 位宽选择:uint16 足够(100Hz 连续流回绕周期 ~10 分钟,接收方用简单窗口判断回绕)

### data 字段布局(Data Layout)

**功能码决定布局,共享公共字段定义**。每个功能码在文档中定义其 `data` 结构:

#### 功能码 0x00: ACK(确认)
```
data = [acked_seq: u16][acked_function_code: u8]
```
- `acked_seq`: 被确认帧的序号(对无序号的消息可填 0)
- `acked_function_code`: 被确认帧的功能码
- 用于回复设了 `flags.bit0=1` 的帧

**第一版行为**: 协议节点收到 flags.bit0=1 的帧,自动构造 0x00 帧回复;发送方收到 0x00 时日志 INFO"已确认",但不等待、不超时重传(第二版实现)

#### 功能码 0x10: 传感器上报(Sensor Data)
```
data = [flags: u8][seq: u16][sensor_id: u8][reading: 4B float, little-endian]
```
- `flags`: bit0 通常=0(传感器数据不需 ACK)
- `seq`: 本传感器的递增序号
- `sensor_id`: 传感器类型/ID(应用自定义,如 1=温度, 2=电压)
- `reading`: 单精度浮点读数

**扩展**: 若传感器返回多个值或复杂结构,可定义新功能码(如 0x20)或在 `reading` 后追加字段(需在 spec 中版本化该布局)

#### 功能码 0x11: 日志(Log Message)
```
data = [flags: u8][seq: u16][log_level: u8][text: UTF-8 bytes]
```
- `flags`: bit0=0(日志不需 ACK)
- `seq`: 日志流的递增序号
- `log_level`: 日志级别(0=DEBUG, 1=INFO, 2=WARN, 3=ERROR, 4=FATAL)
- `text`: UTF-8 编码的日志文本(可含中文),长度 = `len(data) - 4`

**约束**: 整帧 ≤4095B(驱动限制),text 长度 ≤ 约 4080B

#### 功能码 0x12: 控制命令(Control Command)
```
data = [flags: u8][cmd_id: u8][params: bytes]
```
- `flags`: bit0 建议=1(命令需确认)
- `cmd_id`: 命令类型(应用自定义,如 1=启动电机, 2=停止, 3=设置速度)
- `params`: 命令参数(结构由 cmd_id 决定)

**无序号**: 控制命令偶发、低频,不编号(省 2B)

#### 功能码 0x80: 分片帧(Fragmented Frame, 第一版未实现)
```
data = [分片ID: u32][总片数: u16][当前片号: u16, 从0开始][payload: bytes]
```
- `分片ID`: 发送方生成(时间戳+随机数或递增计数),标识一次分片传输
- `总片数`: 本次传输总共多少片
- `当前片号`: 0-based 索引
- `payload`: 本片数据

**第一版行为**: 协议节点收到功能码 0x80 时日志 WARN"分片未实现,frame from station=X",仍转发到 `/protocol/rx`(见 §帧去留清单第 2 行)

**第二版扩展**: 上层节点维护重组状态机(按分片 ID 缓存各片,到齐后拼接、发布完整 payload);发送侧提供自动分片接口(payload >阈值自动切片)

### 文本 vs 二进制数据标记

**功能码隐含格式,不显式标记**:
- 0x11(日志)约定 `text` 字段是 UTF-8 文本
- 0x10(传感器)约定 `reading` 是二进制 float
- 接收方根据功能码决定如何解析 payload,不需要每帧额外带"类型"字段

### 站号策略(Station ID)

**协议层透传,不管**:
- 沿用驱动现有逻辑:
  - `station_id=0`: master 身份(master 发出的帧来源填 0)
  - `station_id=1-247`: 普通设备地址
  - `station_id=248-255`: 保留(驱动层已预留,协议层暂不定义广播)
- 上层协议节点原样转发 `Frame.station_id`,不做额外语义约定

**未来可选扩展**(第二版):
- `station_id=255`: 广播(所有 slave 处理,不回 ACK)
- 协议节点发送侧检查:若目标=255 且 flags.bit0=1,清除 ACK 标志或拒发

### 序号跟踪机制(Sequence Tracking)

协议节点为每个 **(station_id, function_code)** 对维护一个序号追踪器:

```cpp
struct SeqTracker {
    uint16_t expected_seq;  // 期望的下一个序号
    bool initialized;       // 是否已收到第一帧
};
std::map<std::pair<uint8_t, uint8_t>, SeqTracker> trackers_;  // key=(station, func)
```

**行为**:
1. 收到带 seq 字段的帧(0x10/0x11):
   - 若 `!initialized`: 记录 `expected_seq = seq + 1`, `initialized = true`
   - 若 `seq == expected_seq`: 正常,`expected_seq++`(处理回绕:若 expected 溢出则归 0)
   - 若 `seq != expected_seq`:
     - 若 `seq > expected_seq`: 日志 WARN"gap detected: expected={expected}, got={seq}, station={station}, function_code={func}",发布诊断事件,更新 `expected_seq = seq + 1`
     - 若 `seq < expected_seq` 且差值很大(如 expected=100, seq=5): 可能回绕,更新 expected
     - 若 `seq < expected_seq` 且差值很小: 重复帧,日志 DEBUG"duplicate seq={seq}",**丢弃不转发**,诊断计数++
2. 除重复帧外一律转发,包括检测到 gap 的帧:应用可能容忍丢帧(传感器数据),由应用决定是否处理。完整去留规则见 §帧去留清单。

### 错误处理(Error Handling)

#### 帧去留清单(Frame Disposition) — 权威定义

协议节点对每个从驱动收到的帧只有两种处置:**转发**到 `/protocol/rx`,或**丢弃**。本表是唯一的权威定义,本文档其它章节、ticket 和代码注释若提及去留,一律以此表为准,不得各自表述。

| # | 情况 | 处置 | 日志级别 | 诊断计数 |
|---|------|------|----------|----------|
| 1 | 解码成功(0x10 / 0x12) | **转发** | INFO(字段) | — |
| 2 | 未知或未实现功能码(0x00 / 0x11 / 0x80 / 其它) | **转发** | WARN | 未知功能码计数 |
| 3 | data 长度不足,解码器拒绝 | **转发** | ERROR | 解码失败计数 |
| 4 | 序号跳变(gap,疑似链路丢帧) | **转发** | WARN | 丢帧计数 |
| 5 | 序号回绕(uint16 溢出后重新计数) | **转发** | DEBUG | — |
| 6 | **重复帧**(同一 `(station, function_code)` 收到已处理过的 seq) | **丢弃** | DEBUG | 重复帧计数 |

**判据:第一版只丢弃第 6 种。**

第 2–5 种转发的理由一致:协议层解码只是**附加的观察**,不是准入门槛。这一版的应用可以自行解析 `data`(见 §上层节点接口形态,第一版是透明代理),协议层看不懂的帧对应用未必看不懂;而且调试期出现"帧去哪了"的黑洞,比多收几条无用帧代价更高。

第 6 种丢弃的理由不同,是唯一的例外:转发重复帧会让应用**把同一读数处理两次**——这是主动造成错误,而不是仅仅没提供信息。协议层既然已经识别出它是重复的,就有责任不把它递出去。

**第二版**按功能码分发到语义化话题后,解码失败的帧自然进不了对应话题,届时本表需重新审视(第 2、3 种的处置会随之改变),并同步更新此处。

#### 格式非法

见上表第 2、3 行。日志格式:

- **未知功能码**: WARN `"Unknown or unimplemented function_code=0x?? from station=?"`
- **data 长度不足**: ERROR `"Failed to decode function_code=0x??: data size=? (expected >=?)"`

#### 序号异常

见上表第 4、5、6 行,判定逻辑见 §序号跟踪机制。

#### ACK 超时(第一版不实现)
- 第一版:发送方发完即忘,不等 ACK
- 第二版:维护"待 ACK 队列",超时后日志 WARN、诊断话题、可选通知应用

#### 诊断话题
`/protocol/diagnostics` (第二版实现,第一版可选):
- 消息类型:`diagnostic_msgs/DiagnosticStatus` 或自定义 `ProtocolDiagnostics.msg`
- 内容:未知功能码计数、丢帧计数、重复帧计数、每个 station 最后活跃时间
- 发布频率:1Hz 或事件触发

### 协议版本与演进(Versioning)

**无版本协商,靠功能码扩展 + 保守兼容原则**:

1. **已定义功能码的 data 布局不得改**
   - 0x10 第一版是 `[flags][seq][sensor_id][reading]`,第二版不能改成 `[flags][sensor_id][seq][reading]`
   - 要改就用新功能码(如 0x20"传感器上报 v2")

2. **新功能码对旧节点透明**
   - 旧节点收到未知功能码,日志 WARN,不 crash,帧按 §帧去留清单第 2 行仍转发
   - 第一版只定义 0x00/0x10/0x11/0x12,其余保留

3. **flags 保留位必须置 0**
   - 第一版只用 bit0,bit1-7 发送时写 0
   - 第二版若征用 bit2 做新特性,旧节点因忽略 bit2,行为不受影响

4. **升级路径示例**
   - 主机先升到协议 v2(支持 0x80 分片),从机还是 v1
   - 主机发 0x80 给从机→从机日志警告,帧仍转发给应用(§帧去留清单第 2 行),应用自行忽略
   - 主机也支持旧的 0x10-0x12,从机正常工作
   - 等从机升级,0x80 才生效

### 上层节点接口形态(Protocol Node Interface)

#### 第一版(MVP): 透明代理
- 订阅:`/ds10_driver/rx` (ds10_interfaces/Frame)
- 发布:`/protocol/rx` (ds10_interfaces/Frame,data 已按协议解析)
- 订阅:`/protocol/tx` (ds10_interfaces/Frame,应用按协议填 data)
- 发布:`/ds10_driver/tx` (ds10_interfaces/Frame)

**行为**:
- RX 路径:decode data → 提取 flags/seq/payload → 检查序号/重复 → 若需 ACQ 则自动回 0x00 → 发布到 `/protocol/rx`
- TX 路径:应用自己按协议布局填 data,节点透传到驱动(可选:插入序号/flags 辅助函数)

**应用使用**:订阅 `/protocol/rx`,手动解析 `Frame.data`(按功能码 switch-case);发布 `/protocol/tx`,手动填充 data

#### 第二版(生产): 按功能码分发
- 新增语义化话题:
  - `/sensors/data` (SensorReading.msg: sensor_id, reading, timestamp)
  - `/logs/stream` (LogMessage.msg: level, text, timestamp)
  - `/control/commands` (ControlCommand.msg: cmd_id, params)
- RX 路径:decode Frame → 按 function_code 解析 payload → 发布到对应语义话题
- TX 路径:应用发到语义话题 → 节点封装成 Frame(填 function_code, 打包 data) → 发给驱动

**应用使用**:订阅 `/sensors/data` 得到 `SensorReading`,不碰 `Frame`

### 实现语言与依赖
- **C++ 上层节点**(`ds10_protocol` 包):
  - 依赖:`ds10_interfaces`, `diagnostic_msgs`, `rclcpp`
  - C++17,遵循 `ds10_driver` 的编码规范
  - 提供 encode/decode 函数(可复用为库)
- **Python 参考实现**:
  - 改写现有 `ds10_send_file.py` / `ds10_recv_file.py`,按新协议收发
  - 作为非 ROS 环境的参考、以及协议正确性的交叉验证

---

## Testing Decisions

### 好测试的标准
- 只测外部可观察行为,不测内部实现细节
- 业务视角:"发一条应用消息,对端能收到正确解析的字段"

### 测试 Seam

#### Seam 1: 协议 encode/decode 函数边界(gtest)
**测什么**:
- `encode_sensor_data(sensor_id, reading) -> Frame.data` 字节布局正确
- `decode_frame(Frame) -> (flags, seq, payload, function_code)` 提取字段正确
- 边界情况:空 payload、最大长度(~4080B)、flags 各 bit 组合、序号回绕
- 错误帧:未知功能码返回 nullopt、data 长度不足返回错误

**Prior art**: `ds10_driver/test/test_modbus_frame_codec.cpp`(codec gtest)

#### Seam 2: ROS 话题边界 + 协议节点集成(launch_testing)
**测什么**:
- 发布 0x10 传感器帧到 `/protocol/tx` → 协议节点封装 → 驱动发出 → (loopback) → 驱动收到 → 协议节点解封 → `/protocol/rx` 收到正确 sensor_id/reading
- 发布带 flags.bit0=1 的 0x12 帧 → 协议节点自动回 0x00 ACK → 应用收到 ACK 帧
- 序号跳变检测:发 seq=1,3,5 → 日志警告出现 2 次 gap,且 3 帧全部到达 `/protocol/rx`(§帧去留清单第 4 行)
- 重复帧丢弃:发 seq=1,1,2 → `/protocol/rx` 只收到 2 条(seq=1 和 2),§帧去留清单第 6 行
- 未知功能码:发 0xFF 帧 → 日志 WARN,帧仍到达 `/protocol/rx`(§帧去留清单第 2 行)
- 长度不足:发 0x10 但 data 只有 3B → 日志 ERROR,帧仍到达 `/protocol/rx`(§帧去留清单第 3 行)

**Setup**: 用 PTY 假串口连 `ds10_driver` master/slave,`ds10_protocol` 节点夹在中间

**Prior art**: `ds10_driver/test/test_modbus_bus.launch.py`(端到端 launch_testing)

#### Seam 3: Python 参考实现交叉验证(pytest)
**测什么**:
- C++ 协议节点发 0x10 帧 → Python 脚本收到 → 解析出相同 sensor_id/reading
- Python 脚本发 0x11 日志 → C++ 节点收到 → 解析出相同 text
- 确保 C++/Python 对同一协议的理解一致(字节序、字段 offset)

### 不测什么
- `ProtocolNode` 的内部方法(那是实现细节)
- 序号追踪器的数据结构选择(map vs unordered_map,不影响外部行为)
- 日志格式的具体措辞(只测"日志中出现 gap 关键字",不测具体句式)

---

## Out of Scope

### 第一版不实现(推到第二版)
- **分片重组**(0x80):定义格式但不写重组代码
- **ACK 超时重传**:自动回 ACK,但发送方不等、不重传
- **诊断话题**:`/protocol/diagnostics` 可选实现,第一版可以只打日志
- **完整功能码集**:第一版只实现 0x00/0x10/0x11/0x12,其余按需加
- **按功能码分发到语义化话题**:第一版透明代理,第二版深度解析

### 不在协议层职责内
- **DS10 硬件配置**(波特率/SLE 功率/通道绑定):由官方小程序完成
- **Modbus 功能码的业务语义**(读/写寄存器):由业务应用定义
- **应用层业务逻辑**(传感器融合/控制算法):协议只负责数据传输
- **跨帧可靠传输**:依赖 DS10 可靠广播,协议层不做端到端 TCP 式可靠性
- **加密/认证**:明文传输,不涉及安全特性

### 不改动现有组件
- **不修改 `ds10_driver`**:驱动保持"串口 ↔ 帧骨架"职责,协议层独立
- **不修改 `Frame.msg`**:复用现有消息定义,`data` 字段足够承载协议
- **不复用 `modbus_rtu_bus_driver` 逻辑**:语义不同(透传 vs 设备轮询)

---

## Further Notes

### 关键设计权衡

#### 为什么是私有协议,不兼容标准 Modbus?
- DS10 透传 + CRC 试探定长,已偏离标准 Modbus 解析(标准靠功能码+长度字段)
- `Frame.tx_seq` 不入帧(驱动 encode 不编码它),无法端到端传序号
- 承认私有协议,功能码可自由重定义,设计空间更大

#### 为什么序号放 data 里,不改驱动让 tx_seq 入帧?
- 保持驱动职责单一("帧骨架"),不耦合上层协议语义
- 序号是协议层关心的,不是链路层
- 未来若需多套协议共存(不同应用不同序号策略),驱动无需改

#### 为什么第一版只实现 1-2 个功能码?
- 快速验证架构可行(encode/decode/ACK/序号),铺好分层基础
- 避免过早设计:传感器/日志的具体字段可能随业务调整,先用 1-2 个代表性消息验证,其余按需加

#### 为什么不用 Protocol Buffers / JSON?
- Modbus RTU 帧是紧凑二进制(单帧 ≤4095B,包含 CRC/站号开销),Protobuf 序列化有额外开销
- 传感器数据(float)、控制命令(参数)多是固定长度结构,手工打包更高效
- 日志(UTF-8 text)本身就是字节流,不需要 schema
- 若未来有复杂嵌套结构,可在特定功能码(如 0x13)的 payload 里用 Protobuf,协议层只负责外层封装

### 与现有代码的关系
- **复用** `ds10_interfaces/Frame.msg`:不新增消息类型(第一版)
- **复用** CRC-16/MODBUS 实现:可参考 `ds10_driver/modbus_frame_codec.cpp` 的 CRC 函数(虽然协议层不直接算 CRC,但 Python 参考实现可能需要)
- **不复用** `modbus_rtu_bus_driver`:那是完整 Modbus 协议栈,DS10 是透传桥,语义不同

### 部署场景
- **调试阶段**:主从 DS10 接同一台 Jetson,两个 `ds10_driver` 实例(不同 port) + 两个 `ds10_protocol` 实例(不同 namespace)
- **生产阶段**:主机 Jetson 跑 master driver + protocol,15 台从机 Jetson 各跑 slave driver + protocol
- 串口路径:调试期用 by-path(同型号 CH340 by-id 撞车),部署期用 by-id

### 相关文档
- DS10 驱动 spec: `DS10_Modbus/.scratch/ds10-modbus-driver/spec.md`
- 驱动实现状态: memory `ds10-driver-impl-validated.md`
- 串口路径策略: memory `ds10-serial-path-strategy.md`
- CRC-16/MODBUS 参考: `ds10_driver/src/modbus_frame_codec.cpp:27-41`

### 后续工作(超出本 spec)
- 业务协议设计:15 台从机的具体消息类型(哪些传感器、控制命令格式)
- 性能测试:主机对 15 台从机轮询,往返延迟、吞吐率
- 长期运行稳定性:连续运行数天,监控丢帧率、CRC 错误率
- 固件升级:若 DS10 固件更新改变单帧上限(4095B),需复测并调整参数

---

**End of Specification v1**
