
# RTL simulation only (Icarus + cocotb). Run: make
# For Tiny Tapeout CI, use the template's own test/Makefile
# and update PROJECT_SOURCES as required.

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

SRC_DIR = $(abspath $(PWD)/../src)

VERILOG_SOURCES = \
    $(SRC_DIR)/cordic_serial.v \
    $(SRC_DIR)/dsp_fir_iir.v \
    $(SRC_DIR)/tt_um_cordic_dsp.v \
    $(PWD)/tb.v

TOPLEVEL = tb

# cocotb 2.x and 1.x compatibility
COCOTB_TEST_MODULES = test
MODULE = test

# model/ is inside test/
export PYTHONPATH := $(PWD)/model:$(PWD):$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
