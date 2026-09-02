// generated from rosidl_generator_cpp/resource/idl__builder.hpp.em
// with input from ds10_interfaces:msg/Frame.idl
// generated code does not contain a copyright notice

#ifndef DS10_INTERFACES__MSG__DETAIL__FRAME__BUILDER_HPP_
#define DS10_INTERFACES__MSG__DETAIL__FRAME__BUILDER_HPP_

#include <algorithm>
#include <utility>

#include "ds10_interfaces/msg/detail/frame__struct.hpp"
#include "rosidl_runtime_cpp/message_initialization.hpp"


namespace ds10_interfaces
{

namespace msg
{

namespace builder
{

class Init_Frame_rx_seq
{
public:
  explicit Init_Frame_rx_seq(::ds10_interfaces::msg::Frame & msg)
  : msg_(msg)
  {}
  ::ds10_interfaces::msg::Frame rx_seq(::ds10_interfaces::msg::Frame::_rx_seq_type arg)
  {
    msg_.rx_seq = std::move(arg);
    return std::move(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

class Init_Frame_tx_seq
{
public:
  explicit Init_Frame_tx_seq(::ds10_interfaces::msg::Frame & msg)
  : msg_(msg)
  {}
  Init_Frame_rx_seq tx_seq(::ds10_interfaces::msg::Frame::_tx_seq_type arg)
  {
    msg_.tx_seq = std::move(arg);
    return Init_Frame_rx_seq(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

class Init_Frame_data
{
public:
  explicit Init_Frame_data(::ds10_interfaces::msg::Frame & msg)
  : msg_(msg)
  {}
  Init_Frame_tx_seq data(::ds10_interfaces::msg::Frame::_data_type arg)
  {
    msg_.data = std::move(arg);
    return Init_Frame_tx_seq(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

class Init_Frame_function_code
{
public:
  explicit Init_Frame_function_code(::ds10_interfaces::msg::Frame & msg)
  : msg_(msg)
  {}
  Init_Frame_data function_code(::ds10_interfaces::msg::Frame::_function_code_type arg)
  {
    msg_.function_code = std::move(arg);
    return Init_Frame_data(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

class Init_Frame_station_id
{
public:
  explicit Init_Frame_station_id(::ds10_interfaces::msg::Frame & msg)
  : msg_(msg)
  {}
  Init_Frame_function_code station_id(::ds10_interfaces::msg::Frame::_station_id_type arg)
  {
    msg_.station_id = std::move(arg);
    return Init_Frame_function_code(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

class Init_Frame_header
{
public:
  Init_Frame_header()
  : msg_(::rosidl_runtime_cpp::MessageInitialization::SKIP)
  {}
  Init_Frame_station_id header(::ds10_interfaces::msg::Frame::_header_type arg)
  {
    msg_.header = std::move(arg);
    return Init_Frame_station_id(msg_);
  }

private:
  ::ds10_interfaces::msg::Frame msg_;
};

}  // namespace builder

}  // namespace msg

template<typename MessageType>
auto build();

template<>
inline
auto build<::ds10_interfaces::msg::Frame>()
{
  return ds10_interfaces::msg::builder::Init_Frame_header();
}

}  // namespace ds10_interfaces

#endif  // DS10_INTERFACES__MSG__DETAIL__FRAME__BUILDER_HPP_
