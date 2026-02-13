#ifndef ADC_POT_H
#define ADC_POT_H

#include <stdint.h>
#include "pico/types.h"

#define ADC_POT_MAX_RAW 4095u

typedef struct AdcPot AdcPot;

typedef struct {
    uint16_t (*read_raw)(AdcPot *self);
    float (*read_normalized)(AdcPot *self);
} AdcPotOps;

struct AdcPot {
    const char *name;
    uint gpio;
    uint input;
    const AdcPotOps *ops;
};

void adc_pot_system_init(void);
void adc_pot_init(AdcPot *pot, const char *name, uint gpio);
uint16_t adc_pot_read_raw(AdcPot *pot);
float adc_pot_read_normalized(AdcPot *pot);

#endif
