# Generated Cmake Pico project file

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Initialise pico_sdk from installed location
# (note this can come from environment, CMake cache etc)

# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
set(PICO_BOARD pico CACHE STRING "Board type" FORCE)

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../common/devlink_serial.cmake)

project(debug-2 C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

add_executable(debug-2
    debug-2.c
    debug_app.c
)

devlink_serial_enable_for_target(debug-2)
devlink_pio_uart_rx_enable_for_target(debug-2)

pico_set_program_name(debug-2 "debug-2")
pico_set_program_version(debug-2 "0.1")

target_compile_definitions(debug-2 PRIVATE
    PICO_DEFAULT_UART=1
    PICO_DEFAULT_UART_TX_PIN=4
    PICO_DEFAULT_UART_BAUD_RATE=115200
)

pico_enable_stdio_uart(debug-2 1)
pico_enable_stdio_usb(debug-2 0)

target_link_libraries(debug-2
    pico_stdlib
)

target_include_directories(debug-2 PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
    ${CMAKE_CURRENT_LIST_DIR}/../common
)

pico_add_extra_outputs(debug-2)
