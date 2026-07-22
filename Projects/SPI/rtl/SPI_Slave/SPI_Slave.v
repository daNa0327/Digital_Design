module SPI_Slave(
    input reset,
    input start,
    output spi_clk,

    input  [7:0] tx_data, 
    output MISO,

    input  MOSI,
    output [7:0] rx_data,

    output CS,
    output load,
    output shift_en,
    output busy,
    output done
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

        .MISO(MISO)
    );

    SPI_RX r1 (
        .spi_clk(spi_clk),
        .reset(reset),

        .CS(CS),
        .MOSI(MOSI),

        .rx_data(rx_data)
    );
endmodule
