cmake_minimum_required(VERSION 3.8)
project(ds10_relay)

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
find_package(std_msgs REQUIRED)
find_package(ds10_interfaces REQUIRED)

add_library(${PROJECT_NAME}_lib SHARED
  src/transaction.cpp
  src/relay_node.cpp
)
target_include_directories(${PROJECT_NAME}_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(${PROJECT_NAME}_lib
  rclcpp std_msgs ds10_interfaces)

add_executable(relay_node src/main.cpp)
target_link_libraries(relay_node ${PROJECT_NAME}_lib)
ament_target_dependencies(relay_node rclcpp)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  # Test seam 1: pure transaction-header logic, no ROS and no I/O.
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_transaction test/test_transaction.cpp)
  target_link_libraries(test_transaction ${PROJECT_NAME}_lib)
endif()

install(TARGETS ${PROJECT_NAME}_lib relay_node
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY launch config DESTINATION share/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include/)

ament_export_dependencies(rclcpp std_msgs ds10_interfaces)
ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME}_lib)
ament_package()
