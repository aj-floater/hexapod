#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/adc.h"

// Generated template examples retained for later use:
// #include "hardware/i2c.h"
// #include "hardware/uart.h"
//
// // I2C defines
// // This example uses I2C0 on GPIO8 (SDA) and GPIO9 (SCL) at 400kHz.
// #define I2C_PORT i2c0
// #define I2C_SDA 8
// #define I2C_SCL 9
//
// // UART defines
// // By default stdout UART is uart0; template uses uart1 on GPIO4/GPIO5.
// #define UART_ID uart1
// #define BAUD_RATE 115200
// #define UART_TX_PIN 4
// #define UART_RX_PIN 5

// Potentiometer ADC channels for Serial Plotter streaming.
#define ADC1_GPIO 27
#define ADC2_GPIO 28
#define ADC1_INPUT (ADC1_GPIO - 26)
#define ADC2_INPUT (ADC2_GPIO - 26)
#define SAMPLE_DELAY_MS 20

static void init_adc_inputs(void) {
    adc_init();
    adc_gpio_init(ADC1_GPIO);
    adc_gpio_init(ADC2_GPIO);
}

int main(void) {
    stdio_init_all();
    init_adc_inputs();

    // Generated template examples retained but disabled.
    // #if 0
    // // I2C initialisation at 400kHz.
    // i2c_init(I2C_PORT, 400 * 1000);
    // gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
    // gpio_set_function(I2C_SCL, GPIO_FUNC_I2C);
    // gpio_pull_up(I2C_SDA);
    // gpio_pull_up(I2C_SCL);
    //
    // // UART1 initialisation on GPIO4/GPIO5.
    // uart_init(UART_ID, BAUD_RATE);
    // gpio_set_function(UART_TX_PIN, GPIO_FUNC_UART);
    // gpio_set_function(UART_RX_PIN, GPIO_FUNC_UART);
    // uart_puts(UART_ID, "Hello, UART!\\n");
    // #endif

    while (true) {
        adc_select_input(ADC1_INPUT);
        uint16_t adc1_raw = adc_read();

        adc_select_input(ADC2_INPUT);
        uint16_t adc2_raw = adc_read();

        // VS Code Serial Plotter format: >name:value,name:value\r\n
        printf(">adc1_gpio27:%u,adc2_gpio28:%u\r\n", adc1_raw, adc2_raw);
        sleep_ms(SAMPLE_DELAY_MS);
    }
}
