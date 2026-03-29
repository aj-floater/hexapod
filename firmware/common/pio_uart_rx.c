#include "pio_uart_rx.h"

#include "hardware/clocks.h"
#include "pico/stdlib.h"

#include "uart_rx.pio.h"

bool pio_uart_rx_init(PioUartRx *rx, PIO pio, uint pin, uint32_t baud) {
    hard_assert(rx != NULL);
    hard_assert(baud > 0u);

    int claimed_sm = pio_claim_unused_sm(pio, false);
    if (claimed_sm < 0) {
        return false;
    }

    if (!pio_can_add_program(pio, &uart_rx_program)) {
        pio_sm_unclaim(pio, (uint)claimed_sm);
        return false;
    }

    uint offset = pio_add_program(pio, &uart_rx_program);
    float clkdiv = (float)clock_get_hz(clk_sys) / (8.0f * (float)baud);
    uart_rx_program_init(pio, (uint)claimed_sm, offset, pin, clkdiv);

    rx->pio = pio;
    rx->sm = (uint)claimed_sm;
    rx->initialized = true;
    return true;
}

bool pio_uart_rx_try_getc(PioUartRx *rx, uint8_t *out_byte) {
    hard_assert(rx != NULL);
    hard_assert(out_byte != NULL);
    if (!rx->initialized) {
        return false;
    }

    if (pio_sm_is_rx_fifo_empty(rx->pio, rx->sm)) {
        return false;
    }

    uint32_t raw = pio_sm_get(rx->pio, rx->sm);
    *out_byte = (uint8_t)(raw >> 24);
    return true;
}

bool pio_uart_rx_has_pending(const PioUartRx *rx) {
    hard_assert(rx != NULL);
    if (!rx->initialized) {
        return false;
    }

    return !pio_sm_is_rx_fifo_empty(rx->pio, rx->sm);
}
