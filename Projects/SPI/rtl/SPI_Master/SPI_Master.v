module SPI_Master(
    input ck,
    input reset,
    input start,
    output spi_clk,

    input  [7:0] tx_data, 
    output MOSI,

    input  MISO,
    output [7:0] rx_data,

    output CS,
    output load,
    output shift_en,
    output busy,
    output done
);
    clock_divider c1 (
        .ck(ck),
        .reset(reset),

        .spi_clk(spi_clk)
    );
    
    SPI_FSM f1 (
        .spi_clk(spi_clk),
        .reset(reset),
        .start(start),

        .CS(CS),
        .load(load),
        .shift_en(shift_en),
        .busy(busy),
        .done(done)
    );

    SPI_TX t1 (
        .spi_clk(spi_clk),
        .reset(reset),

        .load(load),
        .shift_en(shift_en),
        .tx_data(tx_data), 

        .MOSI(MOSI)
    );

    SPI_RX r1 (
        .spi_clk(spi_clk),
        .reset(reset),

        .CS(CS),
        .MISO(MISO),

        .rx_data(rx_data)
    );
endmodule
