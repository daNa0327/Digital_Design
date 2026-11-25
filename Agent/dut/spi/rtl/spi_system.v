// SPI Master + Slave를 한 모듈로 묶은 평가용 top.
// 이유: Master와 Slave가 둘 다 최상위 후보라 top을 하나로 정할 수 없고, TB/Agent가 한 DUT로 다루기 위함.
module spi_system(
    input ck,                       // 50MHz
    input reset,                    // 비동기, active high
    input start,

    input  [7:0] master_tx_data,
    input  [7:0] slave_tx_data,
    output [7:0] master_rx_data,
    output [7:0] slave_rx_data,

    output spi_clk,
    output CS,
    output MOSI,
    output MISO,
    output busy,
    output done
);
    Master u_master (
        .ck(ck),
        .reset(reset),
        .start(start),
        .spi_clk(spi_clk),

        .tx_data(master_tx_data),
        .MOSI(MOSI),

        .MISO(MISO),
        .rx_data(master_rx_data),

        .CS(CS),
        .load(),
        .shift_en(),
        .busy(busy),
        .done(done)
    );

    Slave u_slave (
        .spi_clk(spi_clk),
        .reset(reset),
        .CS(CS),

        .tx_data(slave_tx_data),
        .MISO(MISO),

        .MOSI(MOSI),
        .rx_data(slave_rx_data)
    );
endmodule
