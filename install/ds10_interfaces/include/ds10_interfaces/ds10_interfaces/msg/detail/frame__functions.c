// generated from rosidl_generator_c/resource/idl__functions.c.em
// with input from ds10_interfaces:msg/Frame.idl
// generated code does not contain a copyright notice
#include "ds10_interfaces/msg/detail/frame__functions.h"

#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "rcutils/allocator.h"


// Include directives for member types
// Member `header`
#include "std_msgs/msg/detail/header__functions.h"
// Member `data`
#include "rosidl_runtime_c/primitives_sequence_functions.h"

bool
ds10_interfaces__msg__Frame__init(ds10_interfaces__msg__Frame * msg)
{
  if (!msg) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__init(&msg->header)) {
    ds10_interfaces__msg__Frame__fini(msg);
    return false;
  }
  // station_id
  // function_code
  // data
  if (!rosidl_runtime_c__uint8__Sequence__init(&msg->data, 0)) {
    ds10_interfaces__msg__Frame__fini(msg);
    return false;
  }
  // tx_seq
  // rx_seq
  return true;
}

void
ds10_interfaces__msg__Frame__fini(ds10_interfaces__msg__Frame * msg)
{
  if (!msg) {
    return;
  }
  // header
  std_msgs__msg__Header__fini(&msg->header);
  // station_id
  // function_code
  // data
  rosidl_runtime_c__uint8__Sequence__fini(&msg->data);
  // tx_seq
  // rx_seq
}

bool
ds10_interfaces__msg__Frame__are_equal(const ds10_interfaces__msg__Frame * lhs, const ds10_interfaces__msg__Frame * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__are_equal(
      &(lhs->header), &(rhs->header)))
  {
    return false;
  }
  // station_id
  if (lhs->station_id != rhs->station_id) {
    return false;
  }
  // function_code
  if (lhs->function_code != rhs->function_code) {
    return false;
  }
  // data
  if (!rosidl_runtime_c__uint8__Sequence__are_equal(
      &(lhs->data), &(rhs->data)))
  {
    return false;
  }
  // tx_seq
  if (lhs->tx_seq != rhs->tx_seq) {
    return false;
  }
  // rx_seq
  if (lhs->rx_seq != rhs->rx_seq) {
    return false;
  }
  return true;
}

bool
ds10_interfaces__msg__Frame__copy(
  const ds10_interfaces__msg__Frame * input,
  ds10_interfaces__msg__Frame * output)
{
  if (!input || !output) {
    return false;
  }
  // header
  if (!std_msgs__msg__Header__copy(
      &(input->header), &(output->header)))
  {
    return false;
  }
  // station_id
  output->station_id = input->station_id;
  // function_code
  output->function_code = input->function_code;
  // data
  if (!rosidl_runtime_c__uint8__Sequence__copy(
      &(input->data), &(output->data)))
  {
    return false;
  }
  // tx_seq
  output->tx_seq = input->tx_seq;
  // rx_seq
  output->rx_seq = input->rx_seq;
  return true;
}

ds10_interfaces__msg__Frame *
ds10_interfaces__msg__Frame__create()
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  ds10_interfaces__msg__Frame * msg = (ds10_interfaces__msg__Frame *)allocator.allocate(sizeof(ds10_interfaces__msg__Frame), allocator.state);
  if (!msg) {
    return NULL;
  }
  memset(msg, 0, sizeof(ds10_interfaces__msg__Frame));
  bool success = ds10_interfaces__msg__Frame__init(msg);
  if (!success) {
    allocator.deallocate(msg, allocator.state);
    return NULL;
  }
  return msg;
}

void
ds10_interfaces__msg__Frame__destroy(ds10_interfaces__msg__Frame * msg)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (msg) {
    ds10_interfaces__msg__Frame__fini(msg);
  }
  allocator.deallocate(msg, allocator.state);
}


bool
ds10_interfaces__msg__Frame__Sequence__init(ds10_interfaces__msg__Frame__Sequence * array, size_t size)
{
  if (!array) {
    return false;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  ds10_interfaces__msg__Frame * data = NULL;

  if (size) {
    data = (ds10_interfaces__msg__Frame *)allocator.zero_allocate(size, sizeof(ds10_interfaces__msg__Frame), allocator.state);
    if (!data) {
      return false;
    }
    // initialize all array elements
    size_t i;
    for (i = 0; i < size; ++i) {
      bool success = ds10_interfaces__msg__Frame__init(&data[i]);
      if (!success) {
        break;
      }
    }
    if (i < size) {
      // if initialization failed finalize the already initialized array elements
      for (; i > 0; --i) {
        ds10_interfaces__msg__Frame__fini(&data[i - 1]);
      }
      allocator.deallocate(data, allocator.state);
      return false;
    }
  }
  array->data = data;
  array->size = size;
  array->capacity = size;
  return true;
}

void
ds10_interfaces__msg__Frame__Sequence__fini(ds10_interfaces__msg__Frame__Sequence * array)
{
  if (!array) {
    return;
  }
  rcutils_allocator_t allocator = rcutils_get_default_allocator();

  if (array->data) {
    // ensure that data and capacity values are consistent
    assert(array->capacity > 0);
    // finalize all array elements
    for (size_t i = 0; i < array->capacity; ++i) {
      ds10_interfaces__msg__Frame__fini(&array->data[i]);
    }
    allocator.deallocate(array->data, allocator.state);
    array->data = NULL;
    array->size = 0;
    array->capacity = 0;
  } else {
    // ensure that data, size, and capacity values are consistent
    assert(0 == array->size);
    assert(0 == array->capacity);
  }
}

ds10_interfaces__msg__Frame__Sequence *
ds10_interfaces__msg__Frame__Sequence__create(size_t size)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  ds10_interfaces__msg__Frame__Sequence * array = (ds10_interfaces__msg__Frame__Sequence *)allocator.allocate(sizeof(ds10_interfaces__msg__Frame__Sequence), allocator.state);
  if (!array) {
    return NULL;
  }
  bool success = ds10_interfaces__msg__Frame__Sequence__init(array, size);
  if (!success) {
    allocator.deallocate(array, allocator.state);
    return NULL;
  }
  return array;
}

void
ds10_interfaces__msg__Frame__Sequence__destroy(ds10_interfaces__msg__Frame__Sequence * array)
{
  rcutils_allocator_t allocator = rcutils_get_default_allocator();
  if (array) {
    ds10_interfaces__msg__Frame__Sequence__fini(array);
  }
  allocator.deallocate(array, allocator.state);
}

bool
ds10_interfaces__msg__Frame__Sequence__are_equal(const ds10_interfaces__msg__Frame__Sequence * lhs, const ds10_interfaces__msg__Frame__Sequence * rhs)
{
  if (!lhs || !rhs) {
    return false;
  }
  if (lhs->size != rhs->size) {
    return false;
  }
  for (size_t i = 0; i < lhs->size; ++i) {
    if (!ds10_interfaces__msg__Frame__are_equal(&(lhs->data[i]), &(rhs->data[i]))) {
      return false;
    }
  }
  return true;
}

bool
ds10_interfaces__msg__Frame__Sequence__copy(
  const ds10_interfaces__msg__Frame__Sequence * input,
  ds10_interfaces__msg__Frame__Sequence * output)
{
  if (!input || !output) {
    return false;
  }
  if (output->capacity < input->size) {
    const size_t allocation_size =
      input->size * sizeof(ds10_interfaces__msg__Frame);
    rcutils_allocator_t allocator = rcutils_get_default_allocator();
    ds10_interfaces__msg__Frame * data =
      (ds10_interfaces__msg__Frame *)allocator.reallocate(
      output->data, allocation_size, allocator.state);
    if (!data) {
      return false;
    }
    // If reallocation succeeded, memory may or may not have been moved
    // to fulfill the allocation request, invalidating output->data.
    output->data = data;
    for (size_t i = output->capacity; i < input->size; ++i) {
      if (!ds10_interfaces__msg__Frame__init(&output->data[i])) {
        // If initialization of any new item fails, roll back
        // all previously initialized items. Existing items
        // in output are to be left unmodified.
        for (; i-- > output->capacity; ) {
          ds10_interfaces__msg__Frame__fini(&output->data[i]);
        }
        return false;
      }
    }
    output->capacity = input->size;
  }
  output->size = input->size;
  for (size_t i = 0; i < input->size; ++i) {
    if (!ds10_interfaces__msg__Frame__copy(
        &(input->data[i]), &(output->data[i])))
    {
      return false;
    }
  }
  return true;
}
