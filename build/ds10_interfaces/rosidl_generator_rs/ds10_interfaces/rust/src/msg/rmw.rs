#[cfg(feature = "serde")]
use serde::{Deserialize, Serialize};


#[link(name = "ds10_interfaces__rosidl_typesupport_c")]
extern "C" {
    fn rosidl_typesupport_c__get_message_type_support_handle__ds10_interfaces__msg__Frame() -> *const std::ffi::c_void;
}

#[link(name = "ds10_interfaces__rosidl_generator_c")]
extern "C" {
    fn ds10_interfaces__msg__Frame__init(msg: *mut Frame) -> bool;
    fn ds10_interfaces__msg__Frame__Sequence__init(seq: *mut rosidl_runtime_rs::Sequence<Frame>, size: usize) -> bool;
    fn ds10_interfaces__msg__Frame__Sequence__fini(seq: *mut rosidl_runtime_rs::Sequence<Frame>);
    fn ds10_interfaces__msg__Frame__Sequence__copy(in_seq: &rosidl_runtime_rs::Sequence<Frame>, out_seq: *mut rosidl_runtime_rs::Sequence<Frame>) -> bool;
}

// Corresponds to ds10_interfaces__msg__Frame
#[cfg_attr(feature = "serde", derive(Deserialize, Serialize))]

/// DS10 星闪 DTU 透传链路上的一条应用层消息。
///
/// 主机侧与从机侧驱动使用同一消息类型, 通过 station_id 区分数据来源/目标。
/// 驱动把 data 组成标准 Modbus RTU 帧写串口 (station_id + function_code + data + CRC),
/// 或从字节流里解出一个完整帧后填充本消息发布。CRC 校验、组帧、定界均由驱动处理,
/// 应用层只关心 station_id / function_code / data 三个业务字段。

#[repr(C)]
#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct Frame {
    /// 收发完成时刻 (stamp) 与串口设备名 (frame_id)。
    pub header: std_msgs::msg::rmw::Header,

    /// Modbus 站号 1-247。
    ///   TX: 主机端填目标从机站号; 从机端此字段被驱动用启动参数 station_id 覆盖。
    ///   RX: 主机端填来源从机站号; 从机端填 0 (表示来自主机)。
    pub station_id: u8,

    /// Modbus 功能码 (如 0x03/0x10)。驱动透传, 不解析其语义。
    pub function_code: u8,

    /// Modbus 数据字段 (不含站号/功能码/CRC), 纯字节。
    /// 长度上限: 整帧 <= 4095B, 即 data <= 约 4080B。超限帧在 TX 侧被拒绝,
    /// 因为 DS10 可靠广播单帧重组天花板实测约 4095B, 超出会被截断。
    pub data: rosidl_runtime_rs::Sequence<u8>,

    /// 端到端对账序号 (应用层可选使用):
    ///   tx_seq: 发送侧填写的递增序号, 随帧透传到对端, 供对端检测丢帧。
    ///   rx_seq: 接收侧驱动递增的本地序号, 主/从各自独立计数。
    pub tx_seq: u32,


    // This member is not documented.
    #[allow(missing_docs)]
    pub rx_seq: u32,

}



impl Default for Frame {
  fn default() -> Self {
    unsafe {
      let mut msg = std::mem::zeroed();
      if !ds10_interfaces__msg__Frame__init(&mut msg as *mut _) {
        panic!("Call to ds10_interfaces__msg__Frame__init() failed");
      }
      msg
    }
  }
}

impl rosidl_runtime_rs::SequenceAlloc for Frame {
  fn sequence_init(seq: &mut rosidl_runtime_rs::Sequence<Self>, size: usize) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { ds10_interfaces__msg__Frame__Sequence__init(seq as *mut _, size) }
  }
  fn sequence_fini(seq: &mut rosidl_runtime_rs::Sequence<Self>) {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { ds10_interfaces__msg__Frame__Sequence__fini(seq as *mut _) }
  }
  fn sequence_copy(in_seq: &rosidl_runtime_rs::Sequence<Self>, out_seq: &mut rosidl_runtime_rs::Sequence<Self>) -> bool {
    // SAFETY: This is safe since the pointer is guaranteed to be valid/initialized.
    unsafe { ds10_interfaces__msg__Frame__Sequence__copy(in_seq, out_seq as *mut _) }
  }
}

impl rosidl_runtime_rs::Message for Frame {
  type RmwMsg = Self;
  fn into_rmw_message(msg_cow: std::borrow::Cow<'_, Self>) -> std::borrow::Cow<'_, Self::RmwMsg> { msg_cow }
  fn from_rmw_message(msg: Self::RmwMsg) -> Self { msg }
}

impl rosidl_runtime_rs::RmwMessage for Frame where Self: Sized {
  const TYPE_NAME: &'static str = "ds10_interfaces/msg/Frame";
  fn get_type_support() -> *const std::ffi::c_void {
    // SAFETY: No preconditions for this function.
    unsafe { rosidl_typesupport_c__get_message_type_support_handle__ds10_interfaces__msg__Frame() }
  }
}


