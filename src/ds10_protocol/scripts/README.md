# Python 参考实现

`scripts/protocol_codec.py` 是 DS10 应用层协议的纯 Python 参考实现。

## 用途

两份用途，两份都是独立于 C++ 实现的：

1. **非 ROS 环境**。一台装了 Python 但没装 ROS 的机器可以通过串口适配器读写总线——适合调试期和离线分析。

2. **交叉验证**。C++ 和 Python 两边从同一段规范文字出发，如果规范有歧义，两边会以不同方式理解它，并在 `protocol_test_vectors.json` 的测试向量上产生分歧。向量文件由**手工按规范推导**，不是用任一实现生成的，所以两边一致地错的可能性被排除。

## 测试

```bash
# Python 侧（自洽 + 向量验证）
python3 -m pytest src/ds10_protocol/test/test_protocol_codec.py -v

# C++ 侧（向量验证 + 自洽）
colcon test --packages-select ds10_protocol
```

97 个 pytest 用例覆盖：两种消息类型的编解码、往返、边界值、inf/nan、负零、长度不足拒绝、尾部字节忽略、向量一致性，以及 IEEE-754 浮点预言机自检。

## 局限

- 只处理 `data` 字段，不处理 Modbus RTU 帧（站号、功能码、CRC、定界属驱动层 `ds10_driver`）。
- 不对 `flags` 保留位做校验：规范要求发送方清零、接收方忽略。
