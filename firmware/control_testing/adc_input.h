#ifndef ADC_INPUT_H
#define ADC_INPUT_H

#include <stdint.h>

#include "pico/types.h"

// Constants
#define ADC_INPUT_MAX_RAW 4095u

// Types
typedef struct {
    uint gpio;
    uint input;
} AdcInput;

// Functions
void adc_input_system_init(void);
void adc_input_init(AdcInput *adc_input, uint gpio);
uint16_t adc_input_read_raw(AdcInput *adc_input);
uint16_t adc_input_read_average_raw(AdcInput *adc_input, uint sample_count);

#endif
