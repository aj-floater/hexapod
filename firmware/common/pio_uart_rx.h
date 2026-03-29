#ifndef PIO_UART_RX_H
#define PIO_UART_RX_H

#include <stdbool.h>
#include <stdint.h>

#include "hardware/pio.h"

typedef struct {
    PIO pio;
    uint sm;
    bool initialized;
} PioUartRx;

bool pio_uart_rx_init(PioUartRx *rx, PIO pio, uint pin, uint32_t baud);
bool pio_uart_rx_try_getc(PioUartRx *rx, uint8_t *out_byte);
bool pio_uart_rx_has_pending(const PioUartRx *rx);

#endif
