#include "telemetry.h"

#include <stdio.h>

#include "pico/stdlib.h"

void telemetry_init(Telemetry *telemetry, uint32_t period_ms) {
    hard_assert(telemetry != NULL);
    hard_assert(period_ms > 0u);

    telemetry->period_ms = period_ms;
    telemetry->next_sample_at = get_absolute_time();
}

bool telemetry_try_sample_one(
    Telemetry *telemetry,
    AdcPot *adc,
    uint16_t *out_raw,
    uint64_t *out_time_us
) {
    hard_assert(telemetry != NULL);
    hard_assert(adc != NULL);
    hard_assert(out_raw != NULL);
    hard_assert(out_time_us != NULL);

    if (!time_reached(telemetry->next_sample_at)) {
        return false;
    }

    *out_raw = adc_pot_read_raw(adc);
    *out_time_us = time_us_64();
    telemetry->next_sample_at = make_timeout_time_ms(telemetry->period_ms);
    return true;
}

bool telemetry_try_sample_three(
    Telemetry *telemetry,
    AdcPot *adc_a,
    AdcPot *adc_b,
    AdcPot *adc_c,
    TelemetrySample *out_sample
) {
    hard_assert(telemetry != NULL);
    hard_assert(adc_a != NULL);
    hard_assert(adc_b != NULL);
    hard_assert(adc_c != NULL);
    hard_assert(out_sample != NULL);

    if (!time_reached(telemetry->next_sample_at)) {
        return false;
    }

    out_sample->adc_a = adc_pot_read_raw(adc_a);
    out_sample->adc_b = adc_pot_read_raw(adc_b);
    out_sample->adc_c = adc_pot_read_raw(adc_c);
    out_sample->time_us = time_us_64();

    telemetry->next_sample_at = make_timeout_time_ms(telemetry->period_ms);
    return true;
}

void telemetry_print_plotter_line(const TelemetrySample *sample) {
    hard_assert(sample != NULL);

    // VS Code Serial Plotter format.
    printf(
        ">adc_a_raw:%u,adc_b_raw:%u,adc_c_raw:%u,time_us:%llu\r\n",
        sample->adc_a,
        sample->adc_b,
        sample->adc_c,
        (unsigned long long)sample->time_us
    );
}
