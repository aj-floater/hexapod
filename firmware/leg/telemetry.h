#ifndef TELEMETRY_H
#define TELEMETRY_H

#include <stdbool.h>
#include <stdint.h>

#include "pico/time.h"

#include "adc_pot.h"

typedef struct {
    uint16_t adc_a;
    uint16_t adc_b;
    uint16_t adc_c;
    uint64_t time_us;
} TelemetrySample;

typedef struct {
    uint32_t period_ms;
    absolute_time_t next_sample_at;
} Telemetry;

void telemetry_init(Telemetry *telemetry, uint32_t period_ms);
bool telemetry_try_sample_one(
    Telemetry *telemetry,
    AdcPot *adc,
    uint16_t *out_raw,
    uint64_t *out_time_us
);
bool telemetry_try_sample_three(
    Telemetry *telemetry,
    AdcPot *adc_a,
    AdcPot *adc_b,
    AdcPot *adc_c,
    TelemetrySample *out_sample
);
void telemetry_print_plotter_line(const TelemetrySample *sample);

#endif
