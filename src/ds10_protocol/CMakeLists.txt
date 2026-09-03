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

# Codec + node library
add_library(${PROJECT_NAME}_lib SHARED
  src/codec.cpp
  src/protocol_bridge_node.cpp
)
target_include_directories(${PROJECT_NAME}_lib PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(${PROJECT_NAME}_lib rclcpp ds10_interfaces)

add_executable(protocol_bridge src/protocol_bridge_main.cpp)
target_link_libraries(protocol_bridge ${PROJECT_NAME}_lib)
ament_target_dependencies(protocol_bridge rclcpp)

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

  # Unit test for sequence tracking (wraparound, gaps, duplicates)
  ament_add_gtest(test_seq_tracker test/test_seq_tracker.cpp)
  target_include_directories(test_seq_tracker PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_seq_tracker ${PROJECT_NAME}_lib)

  # Cross-language wire-format check: this and the Python reference codec
  # both validate against test/protocol_test_vectors.json, so the two
  # implementations cannot drift apart without one of them failing.
  find_package(nlohmann_json REQUIRED)
  ament_add_gtest(test_protocol_vectors test/test_protocol_vectors.cpp)
  target_include_directories(test_protocol_vectors PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
  )
  target_link_libraries(test_protocol_vectors ${PROJECT_NAME}_lib nlohmann_json::nlohmann_json)
  # Absolute path, so the test does not depend on its working directory.
  set_tests_properties(test_protocol_vectors PROPERTIES
    ENVIRONMENT
    "DS10_PROTOCOL_TEST_VECTORS=${CMAKE_CURRENT_SOURCE_DIR}/test/protocol_test_vectors.json")

  # Python reference codec: round trips plus the same shared vectors.
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_protocol_codec test/test_protocol_codec.py)

  # Node-level end-to-end test over real ROS topics.
  find_package(launch_testing_ament_cmake REQUIRED)
  add_launch_test(test/test_protocol_bridge.launch.py)
endif()

install(DIRECTORY include/
  DESTINATION include
)

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
)

install(TARGETS ${PROJECT_NAME}_lib
  EXPORT ${PROJECT_NAME}_lib
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)

install(TARGETS protocol_bridge
  DESTINATION lib/${PROJECT_NAME}
)

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME}_lib)
ament_export_dependencies(rclcpp ds10_interfaces)

ament_package()
