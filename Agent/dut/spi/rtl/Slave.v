module Slave(
    input spi_clk,
    input reset,
    input CS,

    input  [7:0] tx_data,
    output MISO,

    input  MOSI,
    output [7:0] rx_data
);
    Slave_TX t1 (
        .spi_clk(spi_clk),
        .reset(reset),
        .CS(CS),
        .tx_data(tx_data),

        .MISO(MISO)
    );

    Slave_RX r1 (
        .spi_clk(spi_clk),
        .reset(reset),

        .CS(CS),
        .MOSI(MOSI),

        .rx_data(rx_data)
    );
endmodule
