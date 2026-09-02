// generated from rosidl_typesupport_introspection_c/resource/idl__type_support.c.em
// with input from ds10_interfaces:msg/Frame.idl
// generated code does not contain a copyright notice

#include <stddef.h>
#include "ds10_interfaces/msg/detail/frame__rosidl_typesupport_introspection_c.h"
#include "ds10_interfaces/msg/rosidl_typesupport_introspection_c__visibility_control.h"
#include "rosidl_typesupport_introspection_c/field_types.h"
#include "rosidl_typesupport_introspection_c/identifier.h"
#include "rosidl_typesupport_introspection_c/message_introspection.h"
#include "ds10_interfaces/msg/detail/frame__functions.h"
#include "ds10_interfaces/msg/detail/frame__struct.h"


// Include directives for member types
// Member `header`
#include "std_msgs/msg/header.h"
// Member `header`
#include "std_msgs/msg/detail/header__rosidl_typesupport_introspection_c.h"
// Member `data`
#include "rosidl_runtime_c/primitives_sequence_functions.h"

#ifdef __cplusplus
extern "C"
{
#endif

void ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_init_function(
  void * message_memory, enum rosidl_runtime_c__message_initialization _init)
{
  // TODO(karsten1987): initializers are not yet implemented for typesupport c
  // see https://github.com/ros2/ros2/issues/397
  (void) _init;
  ds10_interfaces__msg__Frame__init(message_memory);
}

void ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_fini_function(void * message_memory)
{
  ds10_interfaces__msg__Frame__fini(message_memory);
}

size_t ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__size_function__Frame__data(
  const void * untyped_member)
{
  const rosidl_runtime_c__uint8__Sequence * member =
    (const rosidl_runtime_c__uint8__Sequence *)(untyped_member);
  return member->size;
}

const void * ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_const_function__Frame__data(
  const void * untyped_member, size_t index)
{
  const rosidl_runtime_c__uint8__Sequence * member =
    (const rosidl_runtime_c__uint8__Sequence *)(untyped_member);
  return &member->data[index];
}

void * ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_function__Frame__data(
  void * untyped_member, size_t index)
{
  rosidl_runtime_c__uint8__Sequence * member =
    (rosidl_runtime_c__uint8__Sequence *)(untyped_member);
  return &member->data[index];
}

void ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__fetch_function__Frame__data(
  const void * untyped_member, size_t index, void * untyped_value)
{
  const uint8_t * item =
    ((const uint8_t *)
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_const_function__Frame__data(untyped_member, index));
  uint8_t * value =
    (uint8_t *)(untyped_value);
  *value = *item;
}

void ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__assign_function__Frame__data(
  void * untyped_member, size_t index, const void * untyped_value)
{
  uint8_t * item =
    ((uint8_t *)
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_function__Frame__data(untyped_member, index));
  const uint8_t * value =
    (const uint8_t *)(untyped_value);
  *item = *value;
}

bool ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__resize_function__Frame__data(
  void * untyped_member, size_t size)
{
  rosidl_runtime_c__uint8__Sequence * member =
    (rosidl_runtime_c__uint8__Sequence *)(untyped_member);
  rosidl_runtime_c__uint8__Sequence__fini(member);
  return rosidl_runtime_c__uint8__Sequence__init(member, size);
}

static rosidl_typesupport_introspection_c__MessageMember ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_member_array[6] = {
  {
    "header",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_MESSAGE,  // type
    0,  // upper bound of string
    NULL,  // members of sub message (initialized later)
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, header),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "station_id",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT8,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, station_id),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "function_code",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT8,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, function_code),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "data",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT8,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    true,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, data),  // bytes offset in struct
    NULL,  // default value
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__size_function__Frame__data,  // size() function pointer
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_const_function__Frame__data,  // get_const(index) function pointer
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__get_function__Frame__data,  // get(index) function pointer
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__fetch_function__Frame__data,  // fetch(index, &value) function pointer
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__assign_function__Frame__data,  // assign(index, value) function pointer
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__resize_function__Frame__data  // resize(index) function pointer
  },
  {
    "tx_seq",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT32,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, tx_seq),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  },
  {
    "rx_seq",  // name
    rosidl_typesupport_introspection_c__ROS_TYPE_UINT32,  // type
    0,  // upper bound of string
    NULL,  // members of sub message
    false,  // is array
    0,  // array size
    false,  // is upper bound
    offsetof(ds10_interfaces__msg__Frame, rx_seq),  // bytes offset in struct
    NULL,  // default value
    NULL,  // size() function pointer
    NULL,  // get_const(index) function pointer
    NULL,  // get(index) function pointer
    NULL,  // fetch(index, &value) function pointer
    NULL,  // assign(index, value) function pointer
    NULL  // resize(index) function pointer
  }
};

static const rosidl_typesupport_introspection_c__MessageMembers ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_members = {
  "ds10_interfaces__msg",  // message namespace
  "Frame",  // message name
  6,  // number of fields
  sizeof(ds10_interfaces__msg__Frame),
  ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_member_array,  // message members
  ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_init_function,  // function to initialize message memory (memory has to be allocated)
  ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_fini_function  // function to terminate message instance (will not free memory)
};

// this is not const since it must be initialized on first access
// since C does not allow non-integral compile-time constants
static rosidl_message_type_support_t ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_type_support_handle = {
  0,
  &ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_members,
  get_message_typesupport_handle_function,
};

ROSIDL_TYPESUPPORT_INTROSPECTION_C_EXPORT_ds10_interfaces
const rosidl_message_type_support_t *
ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, ds10_interfaces, msg, Frame)() {
  ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_member_array[0].members_ =
    ROSIDL_TYPESUPPORT_INTERFACE__MESSAGE_SYMBOL_NAME(rosidl_typesupport_introspection_c, std_msgs, msg, Header)();
  if (!ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_type_support_handle.typesupport_identifier) {
    ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_type_support_handle.typesupport_identifier =
      rosidl_typesupport_introspection_c__identifier;
  }
  return &ds10_interfaces__msg__Frame__rosidl_typesupport_introspection_c__Frame_message_type_support_handle;
}
#ifdef __cplusplus
}
#endif
