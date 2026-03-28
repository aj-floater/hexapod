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
set(PICO_BOARD pico CACHE STRING "Board type")

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/../common/devlink_serial.cmake)

project(status_led_demo C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add executable. Default name is the project name, version 0.1

add_executable(status_led_demo status_led_demo.c )
devlink_serial_enable_for_target(status_led_demo)
devlink_pio_uart_rx_enable_for_target(status_led_demo)

pico_set_program_name(status_led_demo "status_led_demo")
pico_set_program_version(status_led_demo "0.1")

target_compile_definitions(status_led_demo PRIVATE
    PICO_DEFAULT_UART=1
    PICO_DEFAULT_UART_TX_PIN=4
    PICO_DEFAULT_UART_RX_PIN=3
    PICO_DEFAULT_UART_BAUD_RATE=115200
)

# Modify the below lines to enable/disable output over UART/USB
pico_enable_stdio_uart(status_led_demo 1)
pico_enable_stdio_usb(status_led_demo 0)

# Add the standard library to the build
target_link_libraries(status_led_demo
        pico_stdlib)

# Add the standard include files to the build
target_include_directories(status_led_demo PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
)

pico_add_extra_outputs(status_led_demo)
