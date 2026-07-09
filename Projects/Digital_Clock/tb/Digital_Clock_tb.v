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


    Digital_Clock dut (
        .ck(ck),
        .reset(reset),

        .h_t(h_t),
        .h_o(h_o),
        .m_t(m_t),
        .m_o(m_o),
        .s_t(s_t),
        .s_o(s_o)
    );

    // Clock 생성 (50MHz)
    always #10 ck = ~ck;

    initial begin
        $dumpfile("sim/wave.vcd");
        $dumpvars(0, Digital_Clock_tb);

        ck = 0; 

        // Reset
        reset = 1;
        #100;
        reset = 0;

        // Default Value = 23:57:00
        dut.h1.hour = 23;
        dut.m1.min = 57;
        dut.s1.sec = 0;

        // Simulation
        #1000000;

        $finish;
    end

    always @(posedge ck) begin
        $display(
            "%d%d : %d%d : %d%d", h_t, h_o, m_t, m_o, s_t, s_o);
    end
endmodule
