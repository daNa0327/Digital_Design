`timescale 1ns/1ps

module UART_tb; 
    reg  ck;
    reg  reset;

    reg  tx_start;
    reg  [7:0] tx_data;
    wire tx;
    wire tx_busy;

    wire rx;
    wire [7:0] rx_data;
    wire data_valid;

    assign rx = tx;

    UART dut(
        .ck(ck),
        .reset(reset),

        .tx_start(tx_start),
        .tx_data(tx_data),
        .tx(tx),
        .tx_busy(tx_busy),

        .rx(rx),
        .data_valid(data_valid),
        .rx_data(rx_data)
    );

    // Clock 생성 (50Hz)
    always #10 ck = ~ck;

    initial begin
        $dumpfile("sim/wave.vcd");
        $dumpvars(0, UART_tb);

        // Initialization 
        ck = 0;
        tx_start = 0;
        tx_data = 0;

        // Reset
        reset = 1;
        #50;
        reset = 0;
        #50;
        
        // Simulation
        tx_data  = 8'b11010101;
        tx_start = 1;
        #20_000;
        tx_start = 0;

        #200_000;
        $finish();
    end
endmodule

/* 향후 개선 필요 사항
   RX 오버샘플링 및 Mid-bit Sampling
*/