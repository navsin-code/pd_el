"""Bit-accurate golden model of cordic_serial (src/cordic_serial.v).

The bit-serial engine is arithmetically identical to the parallel one, so the same model applies.

Every operation mirrors the RTL: 16-bit two's complement, arithmetic right
shifts, simultaneous x/y update, same atan table and gain-compensation steps.
Formats: x,y = Q3.13 ; z = angle with pi = 2**15.
"""
import math

M16 = 0xFFFF
ALPHA = [8192, 4836, 2555, 1297, 651, 326, 163, 81, 41, 20, 10, 5]   # atan(2^-i), pi = 2^15
COMP_STEPS = [(1, 1), (0, 2), (1, 5), (0, 9), (0, 10)]               # (subtract?, k): v +/- (v >> k)


def s16(v):
    """Wrap to signed 16-bit."""
    v &= M16
    return v - 0x10000 if v & 0x8000 else v


def cordic(x, y, z, mode, comp, nsel):
    """mode: 0=rotation 1=vectoring ; comp: gain compensation ; N = 5 + nsel.
    x,y,z may be signed or unsigned 16-bit ints. Returns (x, y, z) as unsigned 16-bit."""
    x, y, z = s16(x), s16(y), z & M16

    # PRE state: rotate by pi if |theta| > pi/2 (rotation) or x < 0 (vectoring)
    flip = (x < 0) if mode else (((z >> 15) ^ (z >> 14)) & 1)
    if flip:
        x, y, z = s16(-x), s16(-y), z ^ 0x8000

    # ITER state
    for i in range(5 + nsel):
        d_pos = (y < 0) if mode else not (z >> 15) & 1
        xs, ys = x >> i, y >> i                       # python >> on ints is arithmetic
        if d_pos:
            x, y, z = s16(x - ys), s16(y + xs), (z - ALPHA[i]) & M16
        else:
            x, y, z = s16(x + ys), s16(y - xs), (z + ALPHA[i]) & M16

    # COMP state: multiply by 1/K with 5 shift-add steps
    if comp:
        for sub, k in COMP_STEPS:
            x = s16(x - (x >> k)) if sub else s16(x + (x >> k))
            y = s16(y - (y >> k)) if sub else s16(y + (y >> k))

    return x & M16, y & M16, z


def busy_cycles(comp, nsel):
    """Clocks between start and done for the bit-serial engine: 16 per pass.
    passes = 1 (pre-rotation) + N (iterations) + 5 (gain steps, optional)."""
    return 16 * (1 + (5 + nsel) + (5 if comp else 0))


def to_q(v, frac=13):
    return int(round(v * (1 << frac)))


def angle_to_z(deg):
    return int(round(deg / 180.0 * 32768)) & M16


if __name__ == "__main__":
    # quick demo: rotate (1,0) by 30 degrees, N=12, compensated
    x, y, z = cordic(to_q(1.0), 0, angle_to_z(30), mode=0, comp=1, nsel=7)
    print("x=%.6f y=%.6f  (expect 0.866025 0.5)" % (s16(x) / 8192, s16(y) / 8192))
    print("raw", s16(x), s16(y), s16(z))
