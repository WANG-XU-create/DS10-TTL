cmake_minimum_required(VERSION 3.8)
project(ds10_driver)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
  set(CMAKE_CXX_EXTENSIONS OFF)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(diagnostic_updater REQUIRED)
find_package(diagnostic_msgs REQUIRED)
find_package(ds10_interfaces REQUIRED)

add_library(${PROJECT_NAME}_lib SHARED
  src/modbus_frame_codec.cpp
  src/serial_port.cpp
  src/ds10_node.cpp
)
target_include_directories(${PROJECT_NAME}_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(${PROJECT_NAME}_lib
  rclcpp diagnostic_updater diagnostic_msgs ds10_interfaces)

add_executable(ds10_node src/main.cpp)
target_link_libraries(ds10_node ${PROJECT_NAME}_lib)
ament_target_dependencies(ds10_node rclcpp)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_modbus_frame_codec test/test_modbus_frame_codec.cpp)
  target_link_libraries(test_modbus_frame_codec ${PROJECT_NAME}_lib)

  # PTY-backed node-level integration test driven from a Python launch file.
  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/test_ds10.launch.py)
endif()

install(TARGETS ${PROJECT_NAME}_lib ds10_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include/)

ament_export_dependencies(rclcpp diagnostic_updater diagnostic_msgs ds10_interfaces)
ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME}_lib)
ament_package()
