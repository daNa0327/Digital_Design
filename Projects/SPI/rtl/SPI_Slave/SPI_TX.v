module Slave_TX (
    input spi_clk,
    input reset,
    input CS,
    input [7:0] tx_data, 

    output MISO
);
    reg [2:0] bit_cnt;

    assign MISO = tx_data[3'd7 - bit_cnt];

    always @(negedge spi_clk or posedge CS or posedge reset) begin
        if (reset) begin
            bit_cnt <= 3'b0;
        end
        else if (CS) begin
            bit_cnt <= 3'b0;
        end
        else begin
            bit_cnt <= bit_cnt + 1'b1;
        end
    end
endmodule
