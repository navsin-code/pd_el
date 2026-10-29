# RTL simulation only (Icarus + cocotb).  Run:  make
# For the Tiny Tapeout CI (which also runs a gate-level job with GATES=yes) use the
# TEMPLATE's own test/Makefile and just edit its PROJECT_SOURCES line to:
#   PROJECT_SOURCES = cordic_serial.v dsp_fir_iir.v tt_um_cordic_dsp.v
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src
VERILOG_SOURCES += $(SRC_DIR)/cordic_serial.v $(SRC_DIR)/dsp_fir_iir.v $(SRC_DIR)/tt_um_cordic_dsp.v $(PWD)/tb.v
TOPLEVEL = tb
# cocotb 2.x uses COCOTB_TEST_MODULES, cocotb 1.x uses MODULE
COCOTB_TEST_MODULES = test
MODULE = test
export PYTHONPATH := $(PWD)/../model:$(PYTHONPATH)
include $(shell cocotb-config --makefiles)/Makefile.sim
