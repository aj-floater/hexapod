#include <stdbool.h>
#include <stdint.h>

#include "pico/stdlib.h"

#include "devlink_serial.h"
#include "pio_uart_rx.h"

#ifndef PICO_DEFAULT_LED_PIN
#error "control_testing requires PICO_DEFAULT_LED_PIN"
#endif

// Constants
#define COMMAND_RX_GPIO 3u          // board RX pin for incoming commands
#define COMMAND_BAUD 115200u        // UART speed
#define COMMAND_BUFFER_LEN 256u     // max line length for a single JSON command
#define COMMAND_IDLE_FLUSH_MS 80u   // how long to wait before flushing a partial line?

// Parameter Ids
enum {
    PARAM_STATUS_LED_ON = 0,
};

// App State
typedef struct {
    bool status_led_on;
} ControlTestingApp;

// Device Description
// tells the devlink library what this device supports
static bool control_testing_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
);
static bool control_testing_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
);

static const DevlinkSerialParamDescriptor g_control_testing_params[] = {
    {
        "status_led.on",
        DEVLINK_SERIAL_TYPE_BOOL,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        false,
        DEVLINK_SERIAL_VALUE_BOOL(false),
        DEVLINK_SERIAL_VALUE_BOOL(true),
        PARAM_STATUS_LED_ON,
    },
};

static const DevlinkSerialDeviceDescriptor g_control_testing_device = {
    .device = "control_testing",
    .firmware = "0.1.0",
    .commands = NULL,
    .command_count = 0u,
    .streams = NULL,
    .stream_count = 0u,
    .params = g_control_testing_params,
    .param_count = count_of(g_control_testing_params),
    .param_getter = control_testing_param_get,
    .param_setter = control_testing_param_set,
};

// LED Helpers

// writes current app state to LED
static void control_testing_apply_status_led(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    gpio_put(PICO_DEFAULT_LED_PIN, app->status_led_on);
}
// sets up the LED GPIO as output
static void control_testing_init(ControlTestingApp *app) {
    hard_assert(app != NULL);

    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    app->status_led_on = false;
    control_testing_apply_status_led(app);
}

// Devlink Parameter Callbacks
// returns the current value of status_led.on
static bool control_testing_param_get(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue *out_value
) {
    ControlTestingApp *app = (ControlTestingApp *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_value != NULL);

    if ((int)param->user_data != PARAM_STATUS_LED_ON) {
        return false;
    }

    *out_value = DEVLINK_SERIAL_VALUE_BOOL(app->status_led_on);
    return true;
}
// accepts a new value, stores it in the app state and updates LED
static bool control_testing_param_set(
    void *context,
    const DevlinkSerialParamDescriptor *param,
    DevlinkSerialValue value,
    const char **out_error_code,
    const char **out_error_message
) {
    ControlTestingApp *app = (ControlTestingApp *)context;

    hard_assert(app != NULL);
    hard_assert(param != NULL);
    hard_assert(out_error_code != NULL);
    hard_assert(out_error_message != NULL);

    *out_error_code = NULL;
    *out_error_message = NULL;

    if ((int)param->user_data != PARAM_STATUS_LED_ON) {
        *out_error_code = "unknown_param";
        *out_error_message = "unknown parameter";
        return false;
    }

    app->status_led_on = value.bool_value;
    control_testing_apply_status_led(app);
    return true;
}

// Command Input - reads incoming UART bytes and turns them into complete JSON command lines
static void control_testing_poll_commands(
    PioUartRx *command_rx,
    DevlinkSerialLineBuffer *line_buffer,
    ControlTestingApp *app,
    char *command_line,
    size_t command_line_size
) {
    uint8_t received_byte = 0u;

    hard_assert(command_rx != NULL);
    hard_assert(line_buffer != NULL);
    hard_assert(app != NULL);
    hard_assert(command_line != NULL);

    while (pio_uart_rx_try_getc(command_rx, &received_byte)) {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_push(
            line_buffer,
            (int)received_byte,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            devlink_serial_handle_command_line(&g_control_testing_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_control_testing_device, "protocol.line_too_long", "error");
        }
    }

    {
        DevlinkSerialLineReadStatus read_status = devlink_serial_line_buffer_flush_if_idle(
            line_buffer,
            command_line,
            command_line_size
        );

        if (read_status == DEVLINK_SERIAL_LINE_READY) {
            devlink_serial_handle_command_line(&g_control_testing_device, app, command_line);
        } else if (read_status == DEVLINK_SERIAL_LINE_OVERFLOW) {
            devlink_serial_print_event(&g_control_testing_device, "protocol.line_too_long", "error");
        }
    }
}

// Main
int main(void) {
    // create runtime objects and buffers
    PioUartRx command_rx = {0};
    ControlTestingApp app = {0};
    DevlinkSerialLineBuffer command_buffer = {0};
    char command_storage[COMMAND_BUFFER_LEN] = {0};
    char command_line[COMMAND_BUFFER_LEN] = {0};

    // start stdio over UART
    stdio_init_all();
    sleep_ms(200u);

    // init the LED
    control_testing_init(&app);
    // start the PIO UART receiver
    if (!pio_uart_rx_init(&command_rx, pio0, COMMAND_RX_GPIO, COMMAND_BAUD)) {
        devlink_serial_print_log(&g_control_testing_device, "error", "pio rx init failed");
        while (true) {
            tight_loop_contents();
        }
    }
    // initialize the line buffer
    devlink_serial_line_buffer_init(
        &command_buffer,
        command_storage,
        sizeof(command_storage),
        COMMAND_IDLE_FLUSH_MS
    );
    // sends devlink discovery messages
    devlink_serial_print_discovery(&g_control_testing_device);
    devlink_serial_print_log(&g_control_testing_device, "info", "control_testing ready");
    devlink_serial_print_event(&g_control_testing_device, "device.ready", "info");

    // main loop
    while (true) {
        control_testing_poll_commands(
            &command_rx,
            &command_buffer,
            &app,
            command_line,
            sizeof(command_line)
        );
        tight_loop_contents();
    }
}
