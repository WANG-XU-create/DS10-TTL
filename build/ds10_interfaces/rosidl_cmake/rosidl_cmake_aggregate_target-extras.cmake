# generated from rosidl_cmake/cmake/rosidl_cmake_aggregate_target-extras.cmake.in

# Create a convenience aggregate target ds10_interfaces::ds10_interfaces
# that links all generated interface targets, so downstream packages can use
# a single modern CMake target name instead of ${ds10_interfaces_TARGETS}.
if(ds10_interfaces_TARGETS AND NOT TARGET ds10_interfaces::ds10_interfaces)
  add_library(ds10_interfaces::ds10_interfaces INTERFACE IMPORTED)
  set_target_properties(ds10_interfaces::ds10_interfaces PROPERTIES
    INTERFACE_LINK_LIBRARIES "${ds10_interfaces_TARGETS}")
endif()
