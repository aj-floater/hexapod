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

project(control_testing C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add executable. Default name is the project name, version 0.1

add_executable(control_testing
    control_testing.c
    servo.c
    adc_input.c
    motor_pwm.c
    position_hold.c
)
devlink_serial_enable_for_target(control_testing)
devlink_pio_uart_rx_enable_for_target(control_testing)

pico_set_program_name(control_testing "control_testing")
pico_set_program_version(control_testing "0.6.0")

target_compile_definitions(control_testing PRIVATE
    PICO_DEFAULT_UART=1
    PICO_DEFAULT_UART_TX_PIN=4
    PICO_DEFAULT_UART_BAUD_RATE=115200
)

# Modify the below lines to enable/disable output over UART/USB
pico_enable_stdio_uart(control_testing 1)
pico_enable_stdio_usb(control_testing 0)

# Add the standard library to the build
target_link_libraries(control_testing
        pico_stdlib
        hardware_adc
        hardware_pwm)

# Add the standard include files to the build
target_include_directories(control_testing PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
        ${CMAKE_CURRENT_LIST_DIR}/../common
)

pico_add_extra_outputs(control_testing)
