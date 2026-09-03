cmake_minimum_required(VERSION 3.8)
project(ds10_protocol)

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
find_package(ds10_interfaces REQUIRED)

# Codec library
add_library(${PROJECT_NAME}_lib src/codec.cpp)
target_include_directories(${PROJECT_NAME}_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  ament_lint_auto_find_test_dependencies()

  find_package(ament_cmake_gtest REQUIRED)

  # Unit test for protocol constants
  ament_add_gtest(test_protocol_constants test/test_protocol_constants.cpp)
  target_include_directories(test_protocol_constants PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_protocol_constants ${PROJECT_NAME}_lib)

  # Unit test for control command codec (0x12)
  ament_add_gtest(test_codec_control_command test/test_codec_control_command.cpp)
  target_include_directories(test_codec_control_command PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_codec_control_command ${PROJECT_NAME}_lib)

  # Unit test for sensor data codec (0x10)
  ament_add_gtest(test_codec_sensor_data test/test_codec_sensor_data.cpp)
  target_include_directories(test_codec_sensor_data PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_codec_sensor_data ${PROJECT_NAME}_lib)

  # Unit test for ACK codec (0x00)
  ament_add_gtest(test_codec_ack test/test_codec_ack.cpp)
  target_include_directories(test_codec_ack PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_codec_ack ${PROJECT_NAME}_lib)
endif()

install(DIRECTORY include/
  DESTINATION include
)

install(TARGETS ${PROJECT_NAME}_lib
  EXPORT ${PROJECT_NAME}_lib
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME}_lib)
ament_export_dependencies(rclcpp ds10_interfaces)

ament_package()
