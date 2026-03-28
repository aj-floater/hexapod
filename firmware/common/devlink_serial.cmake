function(devlink_serial_enable_for_target target_name)
    target_sources(${target_name} PRIVATE
        ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/devlink_serial.c
    )

    target_include_directories(${target_name} PRIVATE
        ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    )
endfunction()

function(devlink_pio_uart_rx_enable_for_target target_name)
    target_sources(${target_name} PRIVATE
        ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/pio_uart_rx.c
    )

    target_include_directories(${target_name} PRIVATE
        ${CMAKE_CURRENT_FUNCTION_LIST_DIR}
    )

    target_link_libraries(${target_name}
        hardware_clocks
        hardware_pio
    )

    pico_generate_pio_header(${target_name}
        ${CMAKE_CURRENT_FUNCTION_LIST_DIR}/uart_rx.pio
    )
endfunction()
