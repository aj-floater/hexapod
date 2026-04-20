cmake_minimum_required(VERSION 3.24)

project(
  hexapod_simulation
  VERSION 0.1.0
  LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set_property(GLOBAL PROPERTY USE_FOLDERS ON)

option(HEXAPOD_SIMULATION_BUILD_TESTS "Build unit tests" ON)

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

include(ThirdPartyVersions)

add_subdirectory(src)

if(HEXAPOD_SIMULATION_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()
