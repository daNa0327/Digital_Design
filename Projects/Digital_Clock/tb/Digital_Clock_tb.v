`timescale 1ns/1ns

module Digital_Clock_tb;
    reg ck;
    reg reset;

    wire [3:0] h_t;
    wire [3:0] h_o;
    wire [3:0] m_t;
    wire [3:0] m_o;
    wire [3:0] s_t;
    wire [3:0] s_o;

    wire [6:0] h_t_seg;
    wire [6:0] h_o_seg;
    wire [6:0] m_t_seg;
    wire [6:0] m_o_seg;
    wire [6:0] s_t_seg;
    wire [6:0] s_o_seg;

    Digital_Clock dut (
        .ck(ck),
        .reset(reset),

        .h_t(h_t),
        .h_o(h_o),
        .m_t(m_t),
        .m_o(m_o),
        .s_t(s_t),
        .s_o(s_o),

        .h_t_seg(h_t_seg),
        .h_o_seg(h_o_seg),
        .m_t_seg(m_t_seg),
        .m_o_seg(m_o_seg),
        .s_t_seg(s_t_seg),
        .s_o_seg(s_o_seg)
    );

    // Clock 생성 (50Hz)
    always #10 ck = ~ck;

    initial begin
        $dumpfile("sim/wave.vcd");
        $dumpvars(0, Digital_Clock_tb);

        ck = 0; 

        // Reset
        reset = 1; 
        #100; 
        reset = 0;

        // Default Value = 23:59:58
        dut.h1.hour = 23;
        dut.m1.min = 59;
        dut.s1.sec = 58;

        // Simulation (5초)
        #5_000_000
        $finish();
    end

    always @(s_o) begin
        $display("%d%d : %d%d : %d%d / %b %b : %b %b : %b %b", h_t, h_o, m_t, m_o, s_t, s_o, h_t_seg, h_o_seg, m_t_seg, m_o_seg, s_t_seg, s_o_seg);
    end
endmodule
