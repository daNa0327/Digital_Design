module Baud_Rate_Generator (
    input ck,
    input reset,

    output reg baud_tick
);
    parameter CLK_FREQ = 50_000_000; // 50MHz
    parameter BAUD_RATE = 115200; // 115,200 bps

    localparam BAUD_CNT = CLK_FREQ / BAUD_RATE - 1; // 오차 약 0.006%

    reg [8:0] count; // 2^9 = 512 > 433

    always @(posedge ck or posedge reset) begin
        if(reset) begin // Asynchronous Reset
            count <= 0;
            baud_tick <= 0;
        end
        else if(count == BAUD_CNT) begin
            count <= 0;
            baud_tick <= 1;
        end
        else begin
            count <= count + 1;
            baud_tick <= 0;
        end
    end
endmodule
