#include "adc_input.h"

#include "hardware/adc.h"
#include "pico/stdlib.h"

// Initializes the ADC peripheral.
void adc_input_system_init(void) {
    adc_init();
}

// Configures one ADC input pin.
void adc_input_init(AdcInput *adc_input, uint gpio) {
    hard_assert(adc_input != NULL);
    hard_assert(gpio >= 26u && gpio <= 28u);

    adc_input->gpio = gpio;
    adc_input->input = gpio - 26u;

    adc_gpio_init(gpio);
}

// Reads one raw ADC sample.
uint16_t adc_input_read_raw(AdcInput *adc_input) {
    hard_assert(adc_input != NULL);

    adc_select_input(adc_input->input);
    return adc_read();
}

// Returns a rounded average sample.
uint16_t adc_input_read_average_raw(AdcInput *adc_input, uint sample_count) {
    uint32_t sum = 0u;

    hard_assert(adc_input != NULL);
    hard_assert(sample_count > 0u);

    for (uint sample_index = 0u; sample_index < sample_count; sample_index++) {
        sum += adc_input_read_raw(adc_input);
    }

    return (uint16_t)((sum + (sample_count / 2u)) / sample_count);
}
