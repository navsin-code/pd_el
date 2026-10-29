`default_nettype none
module dsp_fir_iir (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       sel,
    input  wire [7:0] data_in,
    output reg  [7:0] data_out
);
    reg sel_q;
    reg cfg_ready;
    reg [1:0] mode_q;
    reg [1:0] scale_q;
    reg signed [7:0] h1;
    reg signed [7:0] h2;
    reg signed [7:0] h3;
    reg signed [11:0] iir_prev;
    wire signed [7:0] sample;
    assign sample = $signed(data_in);
    wire signed [11:0] s0;
    wire signed [11:0] s1;
    wire signed [11:0] s2;
    wire signed [11:0] s3;
    assign s0 = {{4{sample[7]}}, sample};
    assign s1 = {{4{h1[7]}}, h1};
    assign s2 = {{4{h2[7]}}, h2};
    assign s3 = {{4{h3[7]}}, h3};
    wire signed [11:0] lp;
    assign lp = ( s0 + (s1 <<< 1) + s1 + (s2 <<< 1) + s2 + s3 ) >>> 3;
    wire signed [11:0] iir_val;
    assign iir_val = s0 + ((iir_prev + (iir_prev <<< 1)) >>> 3);
    reg signed [11:0] core;
    always @(*) begin
        case (mode_q)
            2'd0: begin core = lp; end
            2'd1: begin core = iir_val; end
            2'd2: begin core = s0 - lp; end
            2'd3: begin core = s0; end
            default: begin core = 12'sd0; end
        endcase
    end
    reg signed [14:0] scaled;
    wire signed [14:0] core_extended;
    assign core_extended = $signed({{3{core[11]}}, core});
    always @(*) begin
        case (scale_q)
            2'd0: begin scaled = core_extended >>> 1; end
            2'd1: begin scaled = core_extended; end
            2'd2: begin scaled = core_extended <<< 1; end
            2'd3: begin scaled = core_extended <<< 2; end
            default: begin scaled = core_extended; end
        endcase
    end
    function [7:0] clip8;
        input signed [14:0] val;
        begin
            if (val > 15'sd127) clip8 = 8'h7F;
            else if (val < -15'sd128) clip8 = 8'h80;
            else clip8 = val[7:0];
        end
    endfunction
    always @(posedge clk) begin
        if (!rst_n || !sel) begin
            sel_q <= 1'b0; cfg_ready <= 1'b0; mode_q <= 2'd0; scale_q <= 2'd1;
            h1 <= 8'sd0; h2 <= 8'sd0; h3 <= 8'sd0; iir_prev <= 12'sd0; data_out <= 8'd0;
        end else if (!sel_q) begin
            sel_q <= 1'b1; cfg_ready <= 1'b0; data_out <= 8'd0;
        end else if (!cfg_ready) begin
            mode_q <= data_in[1:0]; scale_q <= data_in[3:2]; cfg_ready <= 1'b1; data_out <= 8'd0;
        end else begin
            data_out <= clip8(scaled);
            h3 <= h2; h2 <= h1; h1 <= sample;
            if (mode_q == 2'd1) iir_prev <= iir_val;
        end
    end
endmodule
`default_nettype wire
