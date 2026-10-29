"""Bit-accurate model of dsp_fir_iir (src/dsp_fir_iir.v).
config byte: din[1:0] = mode (0 FIR LP, 1 IIR LP, 2 FIR HP, 3 bypass), din[3:2] = scale (0.5x,1x,2x,4x)."""


def s(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class Dsp:
    def __init__(self):
        self.h = [0, 0, 0]
        self.ip = 0
        self.mode, self.scale = 0, 1

    def run(self, cfg, samples):
        """Feed samples AFTER the config word; returns the registered output after each sample."""
        self.mode, self.scale = cfg & 3, (cfg >> 2) & 3
        out = []
        for x in samples:
            x = s(x, 8)
            h1, h2, h3 = self.h
            lp = s(x + 3 * h1 + 3 * h2 + h3, 12) >> 3
            iv = s(x + (s(self.ip * 3, 12) >> 3), 12)
            core = [lp, iv, s(x - lp, 12), x][self.mode]
            sc = [core >> 1, core, core << 1, core << 2][self.scale]
            o = 127 if sc > 127 else -128 if sc < -128 else sc
            out.append(o)
            self.h = [x, h1, h2]
            if self.mode == 1:
                self.ip = iv
        return out


def run_stream(cfg, samples):
    return Dsp().run(cfg, samples)


if __name__ == "__main__":
    print("LP unity impulse 64:", run_stream(0b0100, [64, 0, 0, 0, 0]), "(expect 8 24 24 8 0)")
    print("HP unity DC 100    :", run_stream(0b0110, [100] * 6))
    print("IIR unity DC 40    :", run_stream(0b0101, [40] * 14)[-1], "(gain 1.6 -> 63/64)")
