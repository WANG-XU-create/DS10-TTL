// NOLINT: This file starts with a BOM since it contain non-ASCII characters
// generated from rosidl_generator_c/resource/idl__struct.h.em
// with input from ds10_interfaces:msg/Frame.idl
// generated code does not contain a copyright notice

#ifndef DS10_INTERFACES__MSG__DETAIL__FRAME__STRUCT_H_
#define DS10_INTERFACES__MSG__DETAIL__FRAME__STRUCT_H_

#ifdef __cplusplus
extern "C"
{
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>


// Constants defined in the message

// Include directives for member types
// Member 'header'
#include "std_msgs/msg/detail/header__struct.h"
// Member 'data'
#include "rosidl_runtime_c/primitives_sequence.h"

/// Struct defined in msg/Frame in the package ds10_interfaces.
/**
  * DS10 星闪 DTU 透传链路上的一条应用层消息。
  *
  * 主机侧与从机侧驱动使用同一消息类型, 通过 station_id 区分数据来源/目标。
  * 驱动把 data 组成标准 Modbus RTU 帧写串口 (station_id + function_code + data + CRC),
  * 或从字节流里解出一个完整帧后填充本消息发布。CRC 校验、组帧、定界均由驱动处理,
  * 应用层只关心 station_id / function_code / data 三个业务字段。
 */
typedef struct ds10_interfaces__msg__Frame
{
  /// 收发完成时刻 (stamp) 与串口设备名 (frame_id)。
  std_msgs__msg__Header header;
  /// Modbus 站号 1-247。
  ///   TX: 主机端填目标从机站号; 从机端此字段被驱动用启动参数 station_id 覆盖。
  ///   RX: 主机端填来源从机站号; 从机端填 0 (表示来自主机)。
  uint8_t station_id;
  /// Modbus 功能码 (如 0x03/0x10)。驱动透传, 不解析其语义。
  uint8_t function_code;
  /// Modbus 数据字段 (不含站号/功能码/CRC), 纯字节。
  /// 长度上限: 整帧 <= 4095B, 即 data <= 约 4080B。超限帧在 TX 侧被拒绝,
  /// 因为 DS10 可靠广播单帧重组天花板实测约 4095B, 超出会被截断。
  rosidl_runtime_c__uint8__Sequence data;
  /// 端到端对账序号 (应用层可选使用):
  ///   tx_seq: 发送侧填写的递增序号, 随帧透传到对端, 供对端检测丢帧。
  ///   rx_seq: 接收侧驱动递增的本地序号, 主/从各自独立计数。
  uint32_t tx_seq;
  uint32_t rx_seq;
} ds10_interfaces__msg__Frame;

// Struct for a sequence of ds10_interfaces__msg__Frame.
typedef struct ds10_interfaces__msg__Frame__Sequence
{
  ds10_interfaces__msg__Frame * data;
  /// The number of valid items in data
  size_t size;
  /// The number of allocated items in data
  size_t capacity;
} ds10_interfaces__msg__Frame__Sequence;

#ifdef __cplusplus
}
#endif

#endif  // DS10_INTERFACES__MSG__DETAIL__FRAME__STRUCT_H_
