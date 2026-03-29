#include "adc_input.h"

#include "hardware/adc.h"
#include "pico/stdlib.h"

// Setup
void adc_input_system_init(void) {
    adc_init();
}

void adc_input_init(AdcInput *adc_input, uint gpio) {
    hard_assert(adc_input != NULL);
    hard_assert(gpio >= 26u && gpio <= 28u);

    adc_input->gpio = gpio;
    adc_input->input = gpio - 26u;

    adc_gpio_init(gpio);
}

// Reads
uint16_t adc_input_read_raw(AdcInput *adc_input) {
    hard_assert(adc_input != NULL);

    adc_select_input(adc_input->input);
    return adc_read();
}
