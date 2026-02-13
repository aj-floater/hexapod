#include "adc_pot.h"

#include "hardware/adc.h"
#include "pico/stdlib.h"

static uint16_t adc_pot_read_raw_impl(AdcPot *self) {
    hard_assert(self != NULL);
    adc_select_input(self->input);
    return adc_read();
}

static float adc_pot_read_normalized_impl(AdcPot *self) {
    return (float)adc_pot_read_raw_impl(self) / (float)ADC_POT_MAX_RAW;
}

static const AdcPotOps k_adc_pot_ops = {
    .read_raw = adc_pot_read_raw_impl,
    .read_normalized = adc_pot_read_normalized_impl,
};

void adc_pot_system_init(void) {
    adc_init();
}

void adc_pot_init(AdcPot *pot, const char *name, uint gpio) {
    hard_assert(pot != NULL);
    hard_assert(gpio >= 26u && gpio <= 28u);

    pot->name = name;
    pot->gpio = gpio;
    pot->input = gpio - 26u;
    pot->ops = &k_adc_pot_ops;

    adc_gpio_init(gpio);
}

uint16_t adc_pot_read_raw(AdcPot *pot) {
    hard_assert(pot != NULL);
    return pot->ops->read_raw(pot);
}

float adc_pot_read_normalized(AdcPot *pot) {
    hard_assert(pot != NULL);
    return pot->ops->read_normalized(pot);
}
