#include <stdbool.h>
#include <stdint.h>

#include "pico/stdlib.h"
#include "pico/time.h"

#include "adc_input.h"
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
#define ADC_C_GPIO 28u              // adc_c potentiometer input
#define ADC_SAMPLE_PERIOD_MS 20u    // how often to publish pot samples
#define ADC_AVERAGE_SAMPLE_COUNT 16u // how many adc samples to average
#define ADC_LP_ALPHA_DEFAULT_PCT 85u // default low pass alpha
#define ADC_LP_ALPHA_MIN_PCT 1u     // minimum low pass alpha
#define ADC_LP_ALPHA_MAX_PCT 100u   // maximum low pass alpha
#define ADC_C_RAW_MIN 0u            // minimum useful pot reading
#define ADC_C_RAW_MAX 4080u         // maximum useful pot reading
#define ADC_C_DEG_0_RAW 3935u       // rough 0 degree calibration point
#define ADC_C_DEG_180_RAW 285u      // rough 180 degree calibration point
#define ADC_C_MIN_DEG 0u            // minimum reported angle
#define ADC_C_MAX_DEG 180u          // maximum reported angle
#define ANGLE_SOURCE_AVG 0u         // angle uses averaged adc
#define ANGLE_SOURCE_LP 1u          // angle uses low pass adc
#define ANGLE_SOURCE_BOTH 2u        // angle uses both averaged and low pass adc

// Parameter Ids
enum {
    PARAM_STATUS_LED_ON = 0,
    PARAM_FILTER_ALPHA_PCT,
    PARAM_ANGLE_SOURCE_MODE,
};

// App State
typedef struct {
    bool status_led_on;
    AdcInput adc_c;
    bool adc_lp_ready;
    uint8_t adc_lp_alpha_pct;
    uint8_t angle_source_mode;
    uint16_t adc_lp_raw;
    uint32_t adc_raw_sample_seq;
    uint32_t adc_avg_sample_seq;
    uint32_t adc_lp_sample_seq;
    uint32_t adc_angle_avg_sample_seq;
    uint32_t adc_angle_lp_sample_seq;
    absolute_time_t next_adc_sample_at;
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

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_fields[] = {
    {"adc_c_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_avg_fields[] = {
    {"adc_c_avg_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_adc_lp_fields[] = {
    {"adc_c_lp_raw", DEVLINK_SERIAL_TYPE_U16, "adc"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_avg_fields[] = {
    {"adc_c_avg_deg", DEVLINK_SERIAL_TYPE_U16, "deg"},
};

static const DevlinkSerialStreamFieldDescriptor g_control_testing_angle_lp_fields[] = {
    {"adc_c_lp_deg", DEVLINK_SERIAL_TYPE_U16, "deg"},
};

static const DevlinkSerialStreamDescriptor g_control_testing_streams[] = {
    {"control_testing.adc", g_control_testing_adc_fields, count_of(g_control_testing_adc_fields)},
    {"control_testing.adc_avg", g_control_testing_adc_avg_fields, count_of(g_control_testing_adc_avg_fields)},
    {"control_testing.adc_lp", g_control_testing_adc_lp_fields, count_of(g_control_testing_adc_lp_fields)},
    {"control_testing.angle_avg", g_control_testing_angle_avg_fields, count_of(g_control_testing_angle_avg_fields)},
    {"control_testing.angle_lp", g_control_testing_angle_lp_fields, count_of(g_control_testing_angle_lp_fields)},
};

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
    {
        "filter.alpha_pct",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_DEFAULT_PCT),
        true,
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_MIN_PCT),
        DEVLINK_SERIAL_VALUE_U8(ADC_LP_ALPHA_MAX_PCT),
        PARAM_FILTER_ALPHA_PCT,
    },
    {
        "angle.source_mode",
        DEVLINK_SERIAL_TYPE_U8,
        DEVLINK_SERIAL_ACCESS_RW,
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_BOTH),
        true,
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_AVG),
        DEVLINK_SERIAL_VALUE_U8(ANGLE_SOURCE_BOTH),
        PARAM_ANGLE_SOURCE_MODE,
    },
};

static const DevlinkSerialDeviceDescriptor g_control_testing_device = {
    .device = "control_testing",
    .firmware = "0.3.0",
    .commands = NULL,
    .command_count = 0u,
    .streams = g_control_testing_streams,
    .stream_count = count_of(g_control_testing_streams),
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

// ADC Helpers
// sets up the LED GPIO as output
// also sets up adc_c and sample timing
static void control_testing_init(ControlTestingApp *app) {
    absolute_time_t now = get_absolute_time();

    hard_assert(app != NULL);

    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    adc_input_system_init();
    adc_input_init(&app->adc_c, ADC_C_GPIO);

    app->status_led_on = false;
    app->adc_lp_ready = false;
    app->adc_lp_alpha_pct = ADC_LP_ALPHA_DEFAULT_PCT;
    app->angle_source_mode = ANGLE_SOURCE_BOTH;
    app->adc_lp_raw = 0u;
    app->adc_raw_sample_seq = 0u;
    app->adc_avg_sample_seq = 0u;
    app->adc_lp_sample_seq = 0u;
    app->adc_angle_avg_sample_seq = 0u;
    app->adc_angle_lp_sample_seq = 0u;
    app->next_adc_sample_at = now;

    control_testing_apply_status_led(app);
}

// Calibration Helpers
// clamps the raw adc value to the range we can actually use
static uint16_t control_testing_bound_adc_raw(uint16_t raw_value) {
    if (raw_value < ADC_C_RAW_MIN) {
        return ADC_C_RAW_MIN;
    }
    if (raw_value > ADC_C_RAW_MAX) {
        return ADC_C_RAW_MAX;
    }
    return raw_value;
}

// converts the bounded raw value into degrees using the rough calibration points
static uint16_t control_testing_adc_raw_to_deg(uint16_t raw_value) {
    uint32_t numerator = 0u;
    uint32_t denominator = (uint32_t)(ADC_C_DEG_0_RAW - ADC_C_DEG_180_RAW);

    raw_value = control_testing_bound_adc_raw(raw_value);

    if (raw_value >= ADC_C_DEG_0_RAW) {
        return ADC_C_MIN_DEG;
    }
    if (raw_value <= ADC_C_DEG_180_RAW) {
        return ADC_C_MAX_DEG;
    }

    numerator = (uint32_t)(ADC_C_DEG_0_RAW - raw_value) * ADC_C_MAX_DEG;
    return (uint16_t)((numerator + (denominator / 2u)) / denominator);
}

// Filter Helpers
// updates the low pass value using the averaged adc reading
static uint16_t control_testing_update_adc_lp(ControlTestingApp *app, uint16_t avg_raw_value) {
    uint32_t filtered_raw = 0u;
    uint32_t previous_weight = 0u;

    hard_assert(app != NULL);

    if (!app->adc_lp_ready) {
        app->adc_lp_raw = avg_raw_value;
        app->adc_lp_ready = true;
        return app->adc_lp_raw;
    }

    previous_weight = (uint32_t)(ADC_LP_ALPHA_MAX_PCT - app->adc_lp_alpha_pct);
    filtered_raw = ((uint32_t)app->adc_lp_alpha_pct * avg_raw_value)
        + (previous_weight * app->adc_lp_raw);
    app->adc_lp_raw = (uint16_t)((filtered_raw + 50u) / 100u);
    app->adc_lp_raw = control_testing_bound_adc_raw(app->adc_lp_raw);
    return app->adc_lp_raw;
}

// tells the firmware which angle stream or streams should be sent
static bool control_testing_should_emit_angle_avg(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    return app->angle_source_mode == ANGLE_SOURCE_AVG || app->angle_source_mode == ANGLE_SOURCE_BOTH;
}

static bool control_testing_should_emit_angle_lp(const ControlTestingApp *app) {
    hard_assert(app != NULL);
    return app->angle_source_mode == ANGLE_SOURCE_LP || app->angle_source_mode == ANGLE_SOURCE_BOTH;
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
        if ((int)param->user_data == PARAM_FILTER_ALPHA_PCT) {
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->adc_lp_alpha_pct);
            return true;
        }
        if ((int)param->user_data == PARAM_ANGLE_SOURCE_MODE) {
            *out_value = DEVLINK_SERIAL_VALUE_U8(app->angle_source_mode);
            return true;
        }
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
        if ((int)param->user_data == PARAM_FILTER_ALPHA_PCT) {
            app->adc_lp_alpha_pct = (uint8_t)value.u32_value;
            return true;
        }
        if ((int)param->user_data == PARAM_ANGLE_SOURCE_MODE) {
            app->angle_source_mode = (uint8_t)value.u32_value;
            return true;
        }
        *out_error_code = "unknown_param";
        *out_error_message = "unknown parameter";
        return false;
    }

    app->status_led_on = value.bool_value;
    control_testing_apply_status_led(app);
    return true;
}

// Devlink Samples
// sends periodic adc samples so devlink can plot the pot value
static void control_testing_emit_adc_sample(ControlTestingApp *app) {
    uint16_t raw_value = 0u;
    uint16_t avg_raw_value = 0u;
    uint16_t lp_raw_value = 0u;
    uint16_t angle_avg_deg = 0u;
    uint16_t angle_lp_deg = 0u;
    uint64_t sample_time_us = 0u;
    DevlinkSerialValue values[count_of(g_control_testing_adc_fields)];
    DevlinkSerialValue avg_values[count_of(g_control_testing_adc_avg_fields)];
    DevlinkSerialValue lp_values[count_of(g_control_testing_adc_lp_fields)];
    DevlinkSerialValue angle_avg_values[count_of(g_control_testing_angle_avg_fields)];
    DevlinkSerialValue angle_lp_values[count_of(g_control_testing_angle_lp_fields)];

    hard_assert(app != NULL);

    raw_value = control_testing_bound_adc_raw(adc_input_read_raw(&app->adc_c));
    avg_raw_value = control_testing_bound_adc_raw(
        adc_input_read_average_raw(&app->adc_c, ADC_AVERAGE_SAMPLE_COUNT)
    );
    lp_raw_value = control_testing_update_adc_lp(app, avg_raw_value);
    angle_avg_deg = control_testing_adc_raw_to_deg(avg_raw_value);
    angle_lp_deg = control_testing_adc_raw_to_deg(lp_raw_value);
    sample_time_us = time_us_64();

    values[0] = DEVLINK_SERIAL_VALUE_U16(raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[0],
        app->adc_raw_sample_seq++,
        sample_time_us,
        values
    );

    avg_values[0] = DEVLINK_SERIAL_VALUE_U16(avg_raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[1],
        app->adc_avg_sample_seq++,
        sample_time_us,
        avg_values
    );

    lp_values[0] = DEVLINK_SERIAL_VALUE_U16(lp_raw_value);
    devlink_serial_print_sample(
        &g_control_testing_device,
        &g_control_testing_streams[2],
        app->adc_lp_sample_seq++,
        sample_time_us,
        lp_values
    );

    if (control_testing_should_emit_angle_avg(app)) {
        angle_avg_values[0] = DEVLINK_SERIAL_VALUE_U16(angle_avg_deg);
        devlink_serial_print_sample(
            &g_control_testing_device,
            &g_control_testing_streams[3],
            app->adc_angle_avg_sample_seq++,
            sample_time_us,
            angle_avg_values
        );
    }

    if (control_testing_should_emit_angle_lp(app)) {
        angle_lp_values[0] = DEVLINK_SERIAL_VALUE_U16(angle_lp_deg);
        devlink_serial_print_sample(
            &g_control_testing_device,
            &g_control_testing_streams[4],
            app->adc_angle_lp_sample_seq++,
            sample_time_us,
            angle_lp_values
        );
    }
}

static void control_testing_tick(ControlTestingApp *app) {
    hard_assert(app != NULL);

    if (!time_reached(app->next_adc_sample_at)) {
        return;
    }

    control_testing_emit_adc_sample(app);
    app->next_adc_sample_at = make_timeout_time_ms(ADC_SAMPLE_PERIOD_MS);
}

// Command Input
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
    // also init adc_c and sample timing
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
        control_testing_tick(&app);
        tight_loop_contents();
    }
}
