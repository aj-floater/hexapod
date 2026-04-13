#include "pio_uart_rx.h"

#include "hardware/clocks.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#include "uart_rx.pio.h"

#define PIO_UART_RX_RING_BUFFER_SIZE 1024u
#define PIO_UART_RX_RING_BUFFER_MASK (PIO_UART_RX_RING_BUFFER_SIZE - 1u)

typedef struct {
    volatile uint32_t head;
    volatile uint32_t tail;
    volatile uint32_t dropped_count;
    volatile bool active;
    uint8_t bytes[PIO_UART_RX_RING_BUFFER_SIZE];
} PioUartRxSlot;

static_assert(
    (PIO_UART_RX_RING_BUFFER_SIZE & PIO_UART_RX_RING_BUFFER_MASK) == 0u,
    "PIO UART RX ring buffer size must be a power of two"
);

static PioUartRxSlot g_pio_uart_rx_slots[NUM_PIOS * NUM_PIO_STATE_MACHINES] = {0};
static bool g_pio_uart_rx_irq0_handler_installed[NUM_PIOS] = {0};

static PioUartRxSlot *pio_uart_rx_get_slot(PIO pio, uint sm);
static const PioUartRxSlot *pio_uart_rx_get_slot_const(const PIO pio, uint sm);
static void pio_uart_rx_drain_sm_fifo_to_slot(PIO pio, uint sm, PioUartRxSlot *slot);
static void pio_uart_rx_drain_all_slots_for_pio(PIO pio);
static void pio_uart_rx_install_irq0_handler(PIO pio);
static bool pio_uart_rx_try_pop_slot_byte(PioUartRxSlot *slot, uint8_t *out_byte);
static bool pio_uart_rx_try_pop_slot_byte_locked(PioUartRxSlot *slot, uint8_t *out_byte);
static void pio_uart_rx_pio0_irq0_handler(void);
static void pio_uart_rx_pio1_irq0_handler(void);
#if NUM_PIOS > 2
static void pio_uart_rx_pio2_irq0_handler(void);
#endif

bool pio_uart_rx_init(PioUartRx *rx, PIO pio, uint pin, uint32_t baud) {
    PioUartRxSlot *slot = NULL;
    int claimed_sm = -1;
    uint offset = 0u;
    float clkdiv = 0.0f;

    hard_assert(rx != NULL);
    hard_assert(baud > 0u);

    claimed_sm = pio_claim_unused_sm(pio, false);
    if (claimed_sm < 0) {
        return false;
    }

    if (!pio_can_add_program(pio, &uart_rx_program)) {
        pio_sm_unclaim(pio, (uint)claimed_sm);
        return false;
    }

    offset = pio_add_program(pio, &uart_rx_program);
    clkdiv = (float)clock_get_hz(clk_sys) / (8.0f * (float)baud);
    uart_rx_program_init(pio, (uint)claimed_sm, offset, pin, clkdiv);

    slot = pio_uart_rx_get_slot(pio, (uint)claimed_sm);
    hard_assert(slot != NULL);
    slot->head = 0u;
    slot->tail = 0u;
    slot->dropped_count = 0u;
    slot->active = true;

    pio_uart_rx_install_irq0_handler(pio);
    pio_set_irq0_source_enabled(
        pio,
        pio_get_rx_fifo_not_empty_interrupt_source((uint)claimed_sm),
        true
    );

    rx->pio = pio;
    rx->sm = (uint)claimed_sm;
    rx->initialized = true;
    return true;
}

bool pio_uart_rx_try_getc(PioUartRx *rx, uint8_t *out_byte) {
    PioUartRxSlot *slot = NULL;
    uint32_t irq_state = 0u;
    bool success = false;

    hard_assert(rx != NULL);
    hard_assert(out_byte != NULL);
    if (!rx->initialized) {
        return false;
    }

    slot = pio_uart_rx_get_slot(rx->pio, rx->sm);
    hard_assert(slot != NULL);

    if (pio_uart_rx_try_pop_slot_byte(slot, out_byte)) {
        return true;
    }

    irq_state = save_and_disable_interrupts();
    if ((slot->head == slot->tail) && !pio_sm_is_rx_fifo_empty(rx->pio, rx->sm)) {
        pio_uart_rx_drain_sm_fifo_to_slot(rx->pio, rx->sm, slot);
    }
    success = pio_uart_rx_try_pop_slot_byte_locked(slot, out_byte);
    restore_interrupts(irq_state);
    return success;
}

bool pio_uart_rx_has_pending(const PioUartRx *rx) {
    const PioUartRxSlot *slot = NULL;
    uint32_t irq_state = 0u;
    bool has_pending = false;

    hard_assert(rx != NULL);
    if (!rx->initialized) {
        return false;
    }

    slot = pio_uart_rx_get_slot_const(rx->pio, rx->sm);
    hard_assert(slot != NULL);

    irq_state = save_and_disable_interrupts();
    has_pending = (slot->head != slot->tail) || !pio_sm_is_rx_fifo_empty(rx->pio, rx->sm);
    restore_interrupts(irq_state);
    return has_pending;
}

uint32_t pio_uart_rx_take_dropped_count(PioUartRx *rx) {
    PioUartRxSlot *slot = NULL;
    uint32_t irq_state = 0u;
    uint32_t dropped_count = 0u;

    hard_assert(rx != NULL);
    if (!rx->initialized) {
        return 0u;
    }

    slot = pio_uart_rx_get_slot(rx->pio, rx->sm);
    hard_assert(slot != NULL);

    irq_state = save_and_disable_interrupts();
    dropped_count = slot->dropped_count;
    slot->dropped_count = 0u;
    restore_interrupts(irq_state);
    return dropped_count;
}

static PioUartRxSlot *pio_uart_rx_get_slot(PIO pio, uint sm) {
    hard_assert(sm < NUM_PIO_STATE_MACHINES);
    return &g_pio_uart_rx_slots[PIO_NUM(pio) * NUM_PIO_STATE_MACHINES + sm];
}

static const PioUartRxSlot *pio_uart_rx_get_slot_const(const PIO pio, uint sm) {
    hard_assert(sm < NUM_PIO_STATE_MACHINES);
    return &g_pio_uart_rx_slots[PIO_NUM(pio) * NUM_PIO_STATE_MACHINES + sm];
}

static void pio_uart_rx_drain_sm_fifo_to_slot(PIO pio, uint sm, PioUartRxSlot *slot) {
    hard_assert(slot != NULL);

    while (!pio_sm_is_rx_fifo_empty(pio, sm)) {
        uint32_t raw = pio_sm_get(pio, sm);

        if ((slot->head - slot->tail) >= PIO_UART_RX_RING_BUFFER_SIZE) {
            slot->dropped_count += 1u;
            continue;
        }

        slot->bytes[slot->head & PIO_UART_RX_RING_BUFFER_MASK] = (uint8_t)(raw >> 24);
        slot->head += 1u;
    }
}

static void pio_uart_rx_drain_all_slots_for_pio(PIO pio) {
    uint pio_index = PIO_NUM(pio);

    for (uint sm = 0u; sm < NUM_PIO_STATE_MACHINES; ++sm) {
        PioUartRxSlot *slot = &g_pio_uart_rx_slots[pio_index * NUM_PIO_STATE_MACHINES + sm];
        if (!slot->active || pio_sm_is_rx_fifo_empty(pio, sm)) {
            continue;
        }

        pio_uart_rx_drain_sm_fifo_to_slot(pio, sm, slot);
    }
}

static void pio_uart_rx_install_irq0_handler(PIO pio) {
    uint irq_num = PIO_IRQ_NUM(pio, 0u);
    uint pio_index = PIO_NUM(pio);

    if (g_pio_uart_rx_irq0_handler_installed[pio_index]) {
        return;
    }

    switch (pio_index) {
        case 0u:
            irq_add_shared_handler(
                irq_num,
                pio_uart_rx_pio0_irq0_handler,
                PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY
            );
            break;
        case 1u:
            irq_add_shared_handler(
                irq_num,
                pio_uart_rx_pio1_irq0_handler,
                PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY
            );
            break;
#if NUM_PIOS > 2
        case 2u:
            irq_add_shared_handler(
                irq_num,
                pio_uart_rx_pio2_irq0_handler,
                PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY
            );
            break;
#endif
        default:
            hard_assert(false);
            return;
    }

    irq_set_enabled(irq_num, true);
    g_pio_uart_rx_irq0_handler_installed[pio_index] = true;
}

static bool pio_uart_rx_try_pop_slot_byte(PioUartRxSlot *slot, uint8_t *out_byte) {
    uint32_t irq_state = 0u;
    bool success = false;

    hard_assert(slot != NULL);
    hard_assert(out_byte != NULL);

    irq_state = save_and_disable_interrupts();
    success = pio_uart_rx_try_pop_slot_byte_locked(slot, out_byte);
    restore_interrupts(irq_state);
    return success;
}

static bool pio_uart_rx_try_pop_slot_byte_locked(PioUartRxSlot *slot, uint8_t *out_byte) {
    hard_assert(slot != NULL);
    hard_assert(out_byte != NULL);

    if (slot->head == slot->tail) {
        return false;
    }

    *out_byte = slot->bytes[slot->tail & PIO_UART_RX_RING_BUFFER_MASK];
    slot->tail += 1u;
    return true;
}

static void pio_uart_rx_pio0_irq0_handler(void) {
    pio_uart_rx_drain_all_slots_for_pio(pio0);
}

static void pio_uart_rx_pio1_irq0_handler(void) {
    pio_uart_rx_drain_all_slots_for_pio(pio1);
}

#if NUM_PIOS > 2
static void pio_uart_rx_pio2_irq0_handler(void) {
    pio_uart_rx_drain_all_slots_for_pio(pio2);
}
#endif
