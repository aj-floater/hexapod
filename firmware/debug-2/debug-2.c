#include "pico/stdlib.h"

#include "debug_app.h"

int main(void) {
    DebugApp app = {0};

    stdio_init_all();
    sleep_ms(200u);

    debug_app_init(&app);

    while (true) {
        debug_app_poll(&app);
        tight_loop_contents();
    }
}
