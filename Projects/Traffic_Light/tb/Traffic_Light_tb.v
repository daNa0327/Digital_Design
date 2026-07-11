
`timescale 1ns/1ps

module Traffic_Light_tb;
    reg ck;
    reg reset;

    wire HG, HY, HR;
    wire VG, VY, VR;

    Traffic_Light dut (
        .ck(ck),
        .reset(reset),

        .HG(HG),
        .HY(HY),
        .HR(HR),
        .VG(VG),
        .VY(VY),
        .VR(VR)
    );

    // Clock 생성 (50Hz)
    always #10 ck = ~ck;

    initial begin
        $dumpfile("sim/wave.vcd");
        $dumpvars(0, Traffic_Light_tb);

        ck = 0; 

        // Reset
        reset = 1; 
        #1; 
        reset = 0;

        // Simulation
        #500_000_000
        $finish();
    end

    always @(posedge dut.clk_1hz) begin
        $display("State: %b / HTL: %s / TL: %s", 
            dut.state, 
            HG == 1 ? "Green" : HR == 1 ? "Red" : HY == 1 ? "Yellow" : 0, 
            VG == 1 ? "Green" : VR == 1 ? "Red" : VY == 1 ? "Yellow" : 0
        );
    end

endmodule
