# DS10 应用层协议 — 硬件测试计划

**适用版本**: application_protocol_v1.md 第一版(MVP)
**关联 ticket**: 11 — 端到端硬件测试

## 1. 硬件设置

| 角色 | 串口 | station_id | 说明 |
|------|------|-----------|------|
| 主机 | `/dev/ttyUSB0` | 0(隐含) | master role,tx 按 Frame.station_id 路由 |
| 从机 | `/dev/ttyUSB1` | 2 | slave role,tx 被驱动覆盖为 2 |

两台 DS10 星闪 DTU 均接在同一台 Jetson 上,通过无线链路互通。第三个口
`/dev/ttyUSB2` 保留给后续多从机测试。

**权限**: 运行用户需在 `dialout` 组。验证:`ls -l /dev/ttyUSB*` 应显示
`crw-rw---- root dialout`。

## 2. 软件栈

四个节点,由测试脚本统一拉起和关闭:

```
主机侧: ds10_node(master, ttyUSB0) + protocol_bridge(master_bridge)
从机侧: ds10_node(slave,  ttyUSB1) + protocol_bridge(slave_bridge)
```

话题命名**必须两侧分开**,否则两个桥会订阅同一组话题互相打架:

| 节点 | driver_rx | driver_tx | protocol_rx | protocol_tx |
|------|-----------|-----------|-------------|-------------|
| master_bridge | `/ds10_master/rx` | `/ds10_master/tx` | `/master/protocol/rx` | `/master/protocol/tx` |
| slave_bridge | `/ds10_slave/rx` | `/ds10_slave/tx` | `/slave/protocol/rx` | `/slave/protocol/tx` |

## 3. 链路特性(必读)

在写任何断言之前必须理解这两条,否则会把正常现象当成缺陷:

### 3.1 空口回波(Echo / Loopback)

DS10 透传模式下,**每一帧都会被链路两端同时收到,包括发送方自己**。一次
应用层发送在接收侧会产生 2–5 份副本。

这不是驱动 bug,是射频模块的正常工作方式。协议层的序号追踪器把副本判定为
重复帧并丢弃(§帧去留清单第 6 行),这正是该机制的设计目的——**回波是重复帧
判定在真实硬件上的第一个用户**。

**测试影响**: 断言必须写成「期望的行为至少发生了一次」,不能写成精确帧数。
一个断言「恰好收到 3 帧」的测试在真实链路上必然失败。

### 3.2 首帧丢失

协议栈启动后的第一帧通常丢失,发生在 DS10 完成配对握手期间。

**测试影响**: 每轮测试必须先发一个**预热帧**,等链路稳定后再开始计数。预热帧
的 seq 应远离被测序号(本计划用 900),以免存活的预热帧被误认成被测帧。

## 4. 测试场景

| # | 场景 | 通过标准 |
|---|------|---------|
| S1 | 传感器数据上行 | 主机解出 seq=1,2,3,三者之间无 gap 警告 |
| S2 | 控制命令下行 + ACK | 从机解出 0x12(flags=1),且至少自动回复一次 ACK |
| S3 | 序号跳变检测 | 主机**恰好**报告 `11→12` 和 `13→14` 两次 gap,不多不少 |
| S4 | 重复帧丢弃 | 主机记录 `Duplicate seq=20`,且丢弃后 seq=21 不被误判为 gap |
| S5 | 未知功能码 | 从机 WARN `function_code=0xFF`,帧仍转发 |

### 场景设计要点

**S3 断言的是精确集合,不是「包含」**。只检查两条期望警告存在的话,追踪器多
报一次 gap 也会通过——过度敏感的检测器和迟钝的检测器同样是缺陷。

**S3/S4 前需重置序号位置**。追踪器跨场景持续,若不先把序号喂到 9(或 19),
场景切换本身就会产生一次无意义的 gap,「恰好两次」也就无从断言。

**S4 同时断言「丢弃后不产生 gap」**。若追踪器在重复帧上错误推进了期望值,
后续的 seq=21 会被报成 gap。这条否定断言是有实际防护作用的,不是装饰。

## 5. 执行方式

```bash
cd /home/nvidia/DS10_Modbus
source install/setup.bash
python3 src/ds10_protocol/scripts/hardware_protocol_test.py \
    --master-port /dev/ttyUSB0 --slave-port /dev/ttyUSB1 --slave-station 2
```

脚本自行管理四个节点的生命周期,等待 ROS 图发现完成(而非固定 sleep),逐场景
打印判定,并保留四份日志文件路径供报告引用。退出码 0 仅当全部场景 PASS。
