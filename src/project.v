`default_nettype none

module cordic_serial (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] ui,
    output wire [7:0] uo
);

  localparam [1:0] S_RDY = 2'd0, S_PRE = 2'd1, S_ITER = 2'd2, S_COMP = 2'd3;

  reg [15:0] x, y, z;          
  reg [1:0]  state;
  reg [3:0]  k;                
  reg [3:0]  i;                
  reg [3:0]  last_q;           
  reg        mode_q, comp_q, done_q, start_q, flip_q;
  reg        d_q, sgx_q, sgy_q;   
  reg        cx, cy, cz;          

  wire sdi      = ui[0];
  wire sh_en    = ui[1];
  wire start_pe = ui[2] & ~start_q;

  wire busy    = (state != S_RDY);
  wire in_pre  = (state == S_PRE);
  wire in_iter = (state == S_ITER);
  wire in_comp = (state == S_COMP);
  wire first   = (k == 4'd0);
  wire last    = (k == 4'd15);


  localparam [12*14-1:0] ALPHA_ROM = {
      14'd5, 14'd10, 14'd20, 14'd41, 14'd81, 14'd163,
      14'd326, 14'd651, 14'd1297, 14'd2555, 14'd4836, 14'd8192};
  wire [13:0] alpha14   = (i < 4'd12) ? ALPHA_ROM[i*14 +: 14] : 14'd5;
  wire        alpha_bit = (k < 4'd14) ? alpha14[k] : 1'b0;


  reg       c_sub;
  reg [3:0] c_k;
  always @* begin
    case (i[2:0])
      3'd0:    {c_sub, c_k} = {1'b1, 4'd1};
      3'd1:    {c_sub, c_k} = {1'b0, 4'd2};
      3'd2:    {c_sub, c_k} = {1'b1, 4'd5};
      3'd3:    {c_sub, c_k} = {1'b0, 4'd9};
      default: {c_sub, c_k} = {1'b0, 4'd10};
    endcase
  end

  wire [3:0] sh  = in_comp ? c_k : i;
  wire [4:0] ki  = {1'b0, k} + {1'b0, sh};
  wire       ext = ki[4];                       
  wire xtap = ext ? sgx_q : x[sh];
  wire ytap = ext ? sgy_q : y[sh];

  wire sub_x = in_pre ? flip_q : (in_comp ? c_sub : d_q);
  wire sub_y = in_pre ? flip_q : (in_comp ? c_sub : ~d_q);
  wire sub_z = d_q;

  wire a_x = x[0] & ~(in_pre & flip_q);
  wire a_y = y[0] & ~(in_pre & flip_q);
  wire b_x = in_pre ? (x[0] & flip_q) : (in_comp ? xtap : ytap);
  wire b_y = in_pre ? (y[0] & flip_q) : (in_comp ? ytap : xtap);

  wire bb_x  = b_x ^ sub_x;
  wire bb_y  = b_y ^ sub_y;
  wire bb_z  = alpha_bit ^ sub_z;
  wire ci_x  = first ? sub_x : cx;
  wire ci_y  = first ? sub_y : cy;
  wire ci_z  = first ? sub_z : cz;

  wire s_x   = a_x ^ bb_x ^ ci_x;
  wire s_y   = a_y ^ bb_y ^ ci_y;
  wire s_zi  = z[0] ^ bb_z ^ ci_z;
  wire co_x  = (a_x & bb_x) | (a_x & ci_x) | (bb_x & ci_x);
  wire co_y  = (a_y & bb_y) | (a_y & ci_y) | (bb_y & ci_y);
  wire co_z  = (z[0] & bb_z) | (z[0] & ci_z) | (bb_z & ci_z);


  wire s_z   = in_iter ? s_zi : (in_pre ? (z[0] ^ (flip_q & last)) : z[0]);

  wire chain_sh = ~busy & sh_en & ~start_pe;
  wire sh_any   = busy | chain_sh;

  always @(posedge clk) begin
    if (!rst_n) begin
      x <= 16'd0; y <= 16'd0; z <= 16'd0;
    end else if (sh_any) begin
      x <= {busy ? s_x : y[0], x[15:1]};
      y <= {busy ? s_y : z[0], y[15:1]};
      z <= {busy ? s_z : sdi,  z[15:1]};
    end
  end


  always @(posedge clk) begin
    if (!rst_n) begin
      state <= S_RDY; k <= 4'd0; i <= 4'd0; last_q <= 4'd0;
      mode_q <= 1'b0; comp_q <= 1'b0; done_q <= 1'b0; start_q <= 1'b0; flip_q <= 1'b0;
      d_q <= 1'b0; sgx_q <= 1'b0; sgy_q <= 1'b0; cx <= 1'b0; cy <= 1'b0; cz <= 1'b0;
    end else begin
      start_q <= ui[2];
      cx <= co_x; cy <= co_y; cz <= co_z;
      if (busy) k <= k + 4'd1;

      if (busy & last) begin                   
        sgx_q <= s_x;
        sgy_q <= s_y;
        d_q   <= mode_q ? s_y : ~s_z;
      end

      case (state)
        S_RDY: if (start_pe) begin
          mode_q <= ui[3];
          comp_q <= ui[4];
          last_q <= {1'b0, ui[7:5]} + 4'd4;
          flip_q <= ui[3] ? x[15] : (z[15] ^ z[14]);
          done_q <= 1'b0;
          i      <= 4'd0;
          state  <= S_PRE;
        end
        S_PRE: if (last) begin
          state <= S_ITER;
          i     <= 4'd0;
        end
        S_ITER: if (last) begin
          if (i == last_q) begin
            i <= 4'd0;
            if (comp_q) state <= S_COMP;
            else begin state <= S_RDY; done_q <= 1'b1; end
          end else i <= i + 4'd1;
        end
        S_COMP: if (last) begin
          if (i == 4'd4) begin
            i <= 4'd0; state <= S_RDY; done_q <= 1'b1;
          end else i <= i + 4'd1;
        end
      endcase
    end
  end

  assign uo = {i, 1'b0, done_q, busy, x[0]};

endmodule
