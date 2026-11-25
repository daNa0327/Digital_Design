module Slave_RX (
    input spi_clk,
    input reset,

    input CS,
    input MOSI,

    output reg [7:0] rx_data
);
    always @(posedge spi_clk or posedge reset) begin
        if (reset) begin
            rx_data <= 8'b0;
        end
        else if (!CS) begin
            rx_data <= {rx_data[6:0], MOSI};
        end
    end
endmodule
