// generated from rosidl_generator_cpp/resource/idl__traits.hpp.em
// with input from ds10_interfaces:msg/Frame.idl
// generated code does not contain a copyright notice

#ifndef DS10_INTERFACES__MSG__DETAIL__FRAME__TRAITS_HPP_
#define DS10_INTERFACES__MSG__DETAIL__FRAME__TRAITS_HPP_

#include <stdint.h>

#include <sstream>
#include <string>
#include <type_traits>

#include "ds10_interfaces/msg/detail/frame__struct.hpp"
#include "rosidl_runtime_cpp/traits.hpp"

// Include directives for member types
// Member 'header'
#include "std_msgs/msg/detail/header__traits.hpp"

namespace ds10_interfaces
{

namespace msg
{

inline void to_flow_style_yaml(
  const Frame & msg,
  std::ostream & out)
{
  out << "{";
  // member: header
  {
    out << "header: ";
    to_flow_style_yaml(msg.header, out);
    out << ", ";
  }

  // member: station_id
  {
    out << "station_id: ";
    rosidl_generator_traits::value_to_yaml(msg.station_id, out);
    out << ", ";
  }

  // member: function_code
  {
    out << "function_code: ";
    rosidl_generator_traits::value_to_yaml(msg.function_code, out);
    out << ", ";
  }

  // member: data
  {
    if (msg.data.size() == 0) {
      out << "data: []";
    } else {
      out << "data: [";
      size_t pending_items = msg.data.size();
      for (auto item : msg.data) {
        rosidl_generator_traits::value_to_yaml(item, out);
        if (--pending_items > 0) {
          out << ", ";
        }
      }
      out << "]";
    }
    out << ", ";
  }

  // member: tx_seq
  {
    out << "tx_seq: ";
    rosidl_generator_traits::value_to_yaml(msg.tx_seq, out);
    out << ", ";
  }

  // member: rx_seq
  {
    out << "rx_seq: ";
    rosidl_generator_traits::value_to_yaml(msg.rx_seq, out);
  }
  out << "}";
}  // NOLINT(readability/fn_size)

inline void to_block_style_yaml(
  const Frame & msg,
  std::ostream & out, size_t indentation = 0)
{
  // member: header
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "header:\n";
    to_block_style_yaml(msg.header, out, indentation + 2);
  }

  // member: station_id
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "station_id: ";
    rosidl_generator_traits::value_to_yaml(msg.station_id, out);
    out << "\n";
  }

  // member: function_code
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "function_code: ";
    rosidl_generator_traits::value_to_yaml(msg.function_code, out);
    out << "\n";
  }

  // member: data
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    if (msg.data.size() == 0) {
      out << "data: []\n";
    } else {
      out << "data:\n";
      for (auto item : msg.data) {
        if (indentation > 0) {
          out << std::string(indentation, ' ');
        }
        out << "- ";
        rosidl_generator_traits::value_to_yaml(item, out);
        out << "\n";
      }
    }
  }

  // member: tx_seq
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "tx_seq: ";
    rosidl_generator_traits::value_to_yaml(msg.tx_seq, out);
    out << "\n";
  }

  // member: rx_seq
  {
    if (indentation > 0) {
      out << std::string(indentation, ' ');
    }
    out << "rx_seq: ";
    rosidl_generator_traits::value_to_yaml(msg.rx_seq, out);
    out << "\n";
  }
}  // NOLINT(readability/fn_size)

inline std::string to_yaml(const Frame & msg, bool use_flow_style = false)
{
  std::ostringstream out;
  if (use_flow_style) {
    to_flow_style_yaml(msg, out);
  } else {
    to_block_style_yaml(msg, out);
  }
  return out.str();
}

}  // namespace msg

}  // namespace ds10_interfaces

namespace rosidl_generator_traits
{

[[deprecated("use ds10_interfaces::msg::to_block_style_yaml() instead")]]
inline void to_yaml(
  const ds10_interfaces::msg::Frame & msg,
  std::ostream & out, size_t indentation = 0)
{
  ds10_interfaces::msg::to_block_style_yaml(msg, out, indentation);
}

[[deprecated("use ds10_interfaces::msg::to_yaml() instead")]]
inline std::string to_yaml(const ds10_interfaces::msg::Frame & msg)
{
  return ds10_interfaces::msg::to_yaml(msg);
}

template<>
inline const char * data_type<ds10_interfaces::msg::Frame>()
{
  return "ds10_interfaces::msg::Frame";
}

template<>
inline const char * name<ds10_interfaces::msg::Frame>()
{
  return "ds10_interfaces/msg/Frame";
}

template<>
struct has_fixed_size<ds10_interfaces::msg::Frame>
  : std::integral_constant<bool, false> {};

template<>
struct has_bounded_size<ds10_interfaces::msg::Frame>
  : std::integral_constant<bool, false> {};

template<>
struct is_message<ds10_interfaces::msg::Frame>
  : std::true_type {};

}  // namespace rosidl_generator_traits

#endif  // DS10_INTERFACES__MSG__DETAIL__FRAME__TRAITS_HPP_
