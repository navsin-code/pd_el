import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

from cordic_model import cordic, busy_cycles, s16, M16, to_q, angle_to_z
from dsp_model import run_stream, s as sgn


def ui(sdi=0, sh=0, start=0, mode=0, comp=0, nsel=0):
    return sdi | (sh << 1) | (start << 2) | (mode << 3) | (comp << 4) | (nsel << 5)


def bit0(sig):
    """LSB of a (possibly X/Z) signal as 0/1."""
    return 1 if str(sig.value)[-1] == "1" else 0


async def reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)


# ------------------------------------------------------------------ CORDIC engine
async def shift48(dut, tx, cfg):
    """48-bit chain, LSB first: x[15:0], y[15:0], z[15:0]. Returns the bits shifted out."""
    rx = 0
    for k in range(48):
        dut.ui_in.value = ui(sdi=(tx >> k) & 1, sh=1, **cfg)
        await Timer(1, "ns")
        rx |= bit0(dut.uo_out) << k
        await RisingEdge(dut.clk)
    dut.ui_in.value = ui(**cfg)
    return rx


async def run(dut, mode, comp, nsel, x, y, z):
    """Load, start, wait, read. Returns (x, y, z, busy_cycles)."""
    cfg = dict(mode=mode, comp=comp, nsel=nsel)
    await shift48(dut, (x & M16) | ((y & M16) << 16) | ((z & M16) << 32), cfg)
    dut.ui_in.value = ui(start=1, **cfg)
    await RisingEdge(dut.clk)
    dut.ui_in.value = ui(**cfg)
    await Timer(1, "ns")
    cycles = 0
    while (int(dut.uo_out.value) >> 1) & 1:          # busy
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        cycles += 1
    assert (int(dut.uo_out.value) >> 2) & 1, "done flag not set"
    rx = await shift48(dut, 0, cfg)
    return rx & M16, (rx >> 16) & M16, (rx >> 32) & M16, cycles


@cocotb.test()
async def test_bit_exact_vs_model(dut):
    """Bit-serial RTL must match the golden model exactly (raw ints), all modes and N."""
    await reset(dut)
    rnd = random.Random(1234)
    n_tests = 0
    for mode in (0, 1):
        for comp in (0, 1):
            for nsel in range(8):
                for _ in range(12):
                    x = rnd.randint(-9830, 9830)
                    y = rnd.randint(-9830, 9830)
                    z = 0 if mode else rnd.randint(0, M16)
                    got = await run(dut, mode, comp, nsel, x, y, z)
                    exp = cordic(x, y, z, mode, comp, nsel)
                    assert got[:3] == exp, (
                        f"mismatch mode={mode} comp={comp} N={5+nsel} in=({x},{y},{z}) "
                        f"rtl={got[:3]} model={exp}")
                    assert got[3] == busy_cycles(comp, nsel), f"latency {got[3]}"
                    n_tests += 1
    dut._log.info(f"{n_tests} random cases bit-exact")


@cocotb.test()
async def test_extremes_bit_exact(dut):
    """Corner operands: full-scale, zero, negative, MSB-set angles (pre-rotation paths)."""
    await reset(dut)
    vals = [0, 1, -1, 8191, -8192, 12000, -12000, 32767, -32768]
    zs = [0, 1, 0x3FFF, 0x4000, 0x4001, 0x7FFF, 0x8000, 0x8001, 0xBFFF, 0xC000, 0xFFFF]
    rnd = random.Random(5)
    for _ in range(80):
        x, y = rnd.choice(vals), rnd.choice(vals)
        mode = rnd.randint(0, 1)
        z = 0 if mode else rnd.choice(zs)
        comp, nsel = rnd.randint(0, 1), rnd.randint(0, 7)
        got = await run(dut, mode, comp, nsel, x, y, z)
        assert got[:3] == cordic(x, y, z, mode, comp, nsel), (mode, comp, nsel, x, y, z)


@cocotb.test()
async def test_accuracy_vs_float(dut):
    """Compare against floating-point math for N=12, compensation on."""
    await reset(dut)
    rnd = random.Random(7)
    worst_rot = worst_mag = worst_ph = 0.0
    for _ in range(60):
        xr, yr = rnd.uniform(-1.2, 1.2), rnd.uniform(-1.2, 1.2)
        th = rnd.uniform(-math.pi, math.pi * 0.9999)
        x, y, z = to_q(xr), to_q(yr), int(th / math.pi * 32768) & M16
        ox, oy, _, _ = await run(dut, 0, 1, 7, x, y, z)
        t = s16(z) / 32768 * math.pi
        ex = s16(x) * math.cos(t) - s16(y) * math.sin(t)
        ey = s16(x) * math.sin(t) + s16(y) * math.cos(t)
        worst_rot = max(worst_rot, abs(s16(ox) - ex), abs(s16(oy) - ey))
        if math.hypot(xr, yr) >= 0.25:
            mx, my, mz, _ = await run(dut, 1, 1, 7, x, y, 0)
            worst_mag = max(worst_mag, abs(s16(mx) - math.hypot(s16(x), s16(y))))
            ez = math.atan2(s16(y), s16(x)) / math.pi * 32768
            worst_ph = max(worst_ph, abs((s16(mz) - ez + 32768) % 65536 - 32768))
    dut._log.info(f"worst error (LSB): rotation {worst_rot:.1f}, magnitude {worst_mag:.1f}, phase {worst_ph:.1f}")
    assert worst_rot < 20 and worst_mag < 20 and worst_ph < 40


@cocotb.test()
async def test_corner_cases(dut):
    await reset(dut)
    one = 8192
    for deg, ex, ey in [(90, 0, one), (-90, 0, -one), (180, -one, 0), (0, one, 0), (135, -5793, 5793)]:
        ox, oy, _, _ = await run(dut, 0, 1, 7, one, 0, angle_to_z(deg))
        assert abs(s16(ox) - ex) <= 8 and abs(s16(oy) - ey) <= 8, (deg, s16(ox), s16(oy))
    mx, my, mz, _ = await run(dut, 1, 1, 7, -one & M16, 0, 0)
    d = (s16(mz) - 32768 + 32768) % 65536 - 32768
    assert abs(s16(mx) - one) <= 8 and abs(d) <= 16, (s16(mx), s16(mz))


@cocotb.test()
async def test_pipelined_load_unload(dut):
    """Shift new operands in while the previous result shifts out (one 48-clock transfer)."""
    await reset(dut)
    cfg = dict(mode=0, comp=1, nsel=7)
    a = (to_q(0.5) & M16, to_q(0.25) & M16, angle_to_z(40))
    b = (to_q(-0.7) & M16, to_q(0.9) & M16, angle_to_z(-120))
    await shift48(dut, a[0] | (a[1] << 16) | (a[2] << 32), cfg)
    dut.ui_in.value = ui(start=1, **cfg); await RisingEdge(dut.clk)
    dut.ui_in.value = ui(**cfg); await Timer(1, "ns")
    while (int(dut.uo_out.value) >> 1) & 1:
        await RisingEdge(dut.clk); await Timer(1, "ns")
    rx = await shift48(dut, b[0] | (b[1] << 16) | (b[2] << 32), cfg)     # result A out, operands B in
    assert (rx & M16, (rx >> 16) & M16, (rx >> 32) & M16) == cordic(*a, 0, 1, 7)
    dut.ui_in.value = ui(start=1, **cfg); await RisingEdge(dut.clk)
    dut.ui_in.value = ui(**cfg); await Timer(1, "ns")
    while (int(dut.uo_out.value) >> 1) & 1:
        await RisingEdge(dut.clk); await Timer(1, "ns")
    rx = await shift48(dut, 0, cfg)
    assert (rx & M16, (rx >> 16) & M16, (rx >> 32) & M16) == cordic(*b, 0, 1, 7)


# --------------------------------------------------------------------- DSP engine
async def dsp_session(dut, cfg_byte, samples):
    """sel=1 with the config word on ui_in, two edges to latch it, then one sample per clock."""
    dut.uio_in.value = 1
    dut.ui_in.value = cfg_byte
    await RisingEdge(dut.clk)          # DSP enters its session
    await RisingEdge(dut.clk)          # config latched
    outs = []
    for sm in samples:
        dut.ui_in.value = sm & 0xFF
        await RisingEdge(dut.clk)
        await Timer(1, "ns")
        outs.append(sgn(int(dut.uo_out.value), 8))
    dut.uio_in.value = 0               # back to CORDIC
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 3)
    return outs


@cocotb.test()
async def test_dsp_bit_exact_vs_model(dut):
    """All 16 mode/scale combinations, random streams incl. full-scale extremes."""
    await reset(dut)
    rnd = random.Random(99)
    for mode in range(4):
        for scale in range(4):
            cfg = (scale << 2) | mode
            stream = [rnd.choice([-128, 127, rnd.randint(-128, 127), rnd.randint(-40, 40)]) for _ in range(60)]
            got = await dsp_session(dut, cfg, stream)
            exp = run_stream(cfg, stream)
            assert got == exp, f"mode={mode} scale={scale}\n rtl={got}\n mdl={exp}"
    dut._log.info("DSP bit-exact for all 16 configs")


@cocotb.test()
async def test_dsp_directed(dut):
    await reset(dut)
    lp = 0b0100                                              # FIR low-pass, 1x
    assert await dsp_session(dut, lp, [64, 0, 0, 0, 0]) == [8, 24, 24, 8, 0]
    assert (await dsp_session(dut, lp, [100] * 8))[-1] == 100            # unity DC gain
    assert (await dsp_session(dut, lp, [-100] * 8))[-1] == -100          # signed
    assert (await dsp_session(dut, 0b0110, [100] * 8))[-1] == 0          # high-pass rejects DC
    assert (await dsp_session(dut, 0b0101, [40] * 16))[-1] in (62, 63, 64)   # IIR DC gain ~1.6
    assert await dsp_session(dut, 0b1011, [50, -50]) == [100, -100]      # bypass, 2x
    assert await dsp_session(dut, 0b1111, [100, -100]) == [127, -128]    # bypass, 4x -> saturates


@cocotb.test()
async def test_engines_isolated(dut):
    """CORDIC -> DSP -> CORDIC with the same operands: results identical and bit-exact."""
    await reset(dut)
    args = (0, 1, 7, to_q(0.9), to_q(-0.4), angle_to_z(70))
    a = await run(dut, *args)
    await dsp_session(dut, 0b0101, [10, -20, 30, 127, -128, 5])
    b = await run(dut, *args)
    assert a[:3] == b[:3] == cordic(*args[3:], *args[:3])
