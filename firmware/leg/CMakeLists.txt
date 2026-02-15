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
set(toolchainVersion 13_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
set(PICO_BOARD pico CACHE STRING "Board type")

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project(leg C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add executable. Default name is the project name, version 0.1
add_executable(leg
    leg.c
    adc_pot.c
    motor_pwm.c
    telemetry.c
)

pico_set_program_name(leg "leg")
pico_set_program_version(leg "0.1")

# UART mapping for Pico Probe serial output.
target_compile_definitions(leg PRIVATE
    PICO_DEFAULT_UART=1
    PICO_DEFAULT_UART_TX_PIN=4
    PICO_DEFAULT_UART_RX_PIN=3
    PICO_DEFAULT_UART_BAUD_RATE=112500
)

# Modify the below lines to enable/disable output over UART/USB
pico_enable_stdio_uart(leg 1)
pico_enable_stdio_usb(leg 0)

# Add requested libraries.
target_link_libraries(leg
    pico_stdlib
    hardware_adc
    hardware_pwm
    hardware_clocks
    # hardware_i2c
)

# Add the standard include files to the build
target_include_directories(leg PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

pico_add_extra_outputs(leg)
