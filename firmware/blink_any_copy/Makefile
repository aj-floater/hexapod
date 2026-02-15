SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

PROJECT_DIR := .
BUILD_DIR := build-blink_any_copy
TARGET := blink_any
ELF := $(BUILD_DIR)/$(TARGET).elf

HOME_DIR := $(HOME)
PICO_TOOLS_HOME ?= $(HOME_DIR)/.pico-sdk
PICO_TOOLCHAIN_BIN ?= $(PICO_TOOLS_HOME)/toolchain/13_2_Rel1/bin
CMAKE_BIN ?= $(PICO_TOOLS_HOME)/cmake/v3.31.5/bin/cmake
NINJA_BIN ?= $(PICO_TOOLS_HOME)/ninja/v1.12.1
GDB_BIN ?= $(PICO_TOOLCHAIN_BIN)/arm-none-eabi-gdb
OPENOCD_BIN ?= $(PICO_TOOLS_HOME)/openocd/0.12.0+dev/openocd
OPENOCD_SCRIPTS ?= $(PICO_TOOLS_HOME)/openocd/0.12.0+dev/scripts
TOOL_PATH := $(PICO_TOOLCHAIN_BIN):$(NINJA_BIN):$(PICO_TOOLS_HOME)/picotool/2.2.0-a4/picotool:$(PATH)

# Pico Probe defaults.
OPENOCD_INTERFACE ?= interface/cmsis-dap.cfg
OPENOCD_TARGET ?= target/rp2040.cfg
OPENOCD_ADAPTER_SPEED ?= 5000

.PHONY: default list check build flash openocd debug clean

default: list

list:
	@printf "Available targets:\n"
	@printf "  make check   - verify expected Pico tools are present\n"
	@printf "  make build   - configure + build Debug firmware\n"
	@printf "  make flash   - build then flash with OpenOCD\n"
	@printf "  make openocd - run OpenOCD gdbserver\n"
	@printf "  make debug   - build, launch OpenOCD, attach gdb\n"
	@printf "  make clean   - remove build artifacts\n"

check:
	@test -x "$(CMAKE_BIN)" || (echo "Missing cmake: $(CMAKE_BIN)" && exit 1)
	@test -x "$(GDB_BIN)" || (echo "Missing gdb: $(GDB_BIN)" && exit 1)
	@test -x "$(OPENOCD_BIN)" || (echo "Missing openocd: $(OPENOCD_BIN)" && exit 1)
	@test -d "$(OPENOCD_SCRIPTS)" || (echo "Missing OpenOCD scripts dir: $(OPENOCD_SCRIPTS)" && exit 1)
	@echo "Tool check passed."

build:
	PATH="$(TOOL_PATH)" "$(CMAKE_BIN)" -S "$(PROJECT_DIR)" -B "$(BUILD_DIR)" -G Ninja \
		-DCMAKE_BUILD_TYPE=Debug -DPICO_SDK_FETCH_FROM_GIT=ON
	PATH="$(TOOL_PATH)" "$(CMAKE_BIN)" --build "$(BUILD_DIR)" -j

flash: build
	"$(OPENOCD_BIN)" -s "$(OPENOCD_SCRIPTS)" -f "$(OPENOCD_INTERFACE)" -f "$(OPENOCD_TARGET)" \
		-c "adapter speed $(OPENOCD_ADAPTER_SPEED)" \
		-c "program $(ELF) verify reset exit"

openocd:
	"$(OPENOCD_BIN)" -s "$(OPENOCD_SCRIPTS)" -f "$(OPENOCD_INTERFACE)" -f "$(OPENOCD_TARGET)" \
		-c "adapter speed $(OPENOCD_ADAPTER_SPEED)"

debug: build
	"$(OPENOCD_BIN)" -s "$(OPENOCD_SCRIPTS)" -f "$(OPENOCD_INTERFACE)" -f "$(OPENOCD_TARGET)" -c "adapter speed $(OPENOCD_ADAPTER_SPEED)" > /tmp/openocd-$(TARGET).log 2>&1 & \
	ocd_pid=$$!; \
	trap 'kill "$$ocd_pid" 2>/dev/null || true' EXIT; \
	sleep 1; \
	"$(GDB_BIN)" "$(ELF)" \
		-ex "target extended-remote :3333" \
		-ex "monitor reset halt"

clean:
	rm -rf "$(BUILD_DIR)"
