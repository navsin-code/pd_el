// Tiny Tapeout top: bit-serial CORDIC + FIR/IIR DSP sharing the same pins.
//
//   uio_in[0] = sel : 0 = CORDIC engine, 1 = DSP engine
//   (change sel only while the selected engine is idle)
//
//   sel = 0 : CORDIC.  ui_in / uo_out as documented in cordic_serial.v
//   sel = 1 : DSP.  Drive sel = 1 with the config word on ui_in
//             (din[1:0] = mode: 0 FIR low-pass, 1 IIR low-pass, 2 FIR high-pass, 3 bypass;
//              din[3:2] = scale: 0 = 0.5x, 1 = 1x, 2 = 2x, 3 = 4x),
//             wait two clock edges (config is latched on the second), then present one
//             signed 8-bit sample per clock on ui_in; uo_out is the filtered sample,
//             registered (appears one clock after its input).
//   The unselected engine is held idle.

`default_nettype none

module tt_um_cordic_dsp (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  reg sel_q;
  always @(posedge clk) begin
    if (!rst_n) sel_q <= 1'b0;
    else        sel_q <= uio_in[0];
  end

  wire [7:0] uo_cordic;
  cordic_serial u_cordic (
      .clk  (clk),
      .rst_n(rst_n),
      .ui   ((sel_q | uio_in[0]) ? 8'h00 : ui_in),   // raw pin too: the config word must never reach the CORDIC
      .uo   (uo_cordic)
  );

  wire [7:0] dsp_out;
  dsp_fir_iir u_dsp (
      .clk     (clk),
      .rst_n   (rst_n),
      .sel     (uio_in[0]),     // raw pin: the DSP registers it itself (2-edge protocol)
      .data_in (ui_in),
      .data_out(dsp_out)
  );

  assign uo_out  = sel_q ? dsp_out : uo_cordic;
  assign uio_out = 8'h00;
  assign uio_oe  = 8'h00;

  wire _unused = &{ena, uio_in[7:1], 1'b0};

endmodule
