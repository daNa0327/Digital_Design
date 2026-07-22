`timescale 1ns/1ps

module Master_Slave_tb;

    reg ck;
    reg reset;
    reg start;

    reg  [7:0] master_tx_data;
    wire [7:0] master_rx_data;

    reg  [7:0] slave_tx_data;
    wire [7:0] slave_rx_data;

    // SPI Interconnect Signals
    wire spi_clk;
    wire CS;
    wire MOSI;
    wire MISO;

    wire busy;
    wire done;

    // 1. Master Instantiation
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
        .busy(busy),
        .done(done)
    );

    // 2. Slave Instantiation
    Slave u_slave (
        .spi_clk(spi_clk),
        .reset(reset),
        .CS(CS),

        .tx_data(slave_tx_data),
        .MISO(MISO),

        .MOSI(MOSI),
        .rx_data(slave_rx_data)
    );

    // 50MHz Clock Generation
    initial begin
        ck = 0;
        forever #10 ck = ~ck;
    end

    // Test Scenario
    initial begin
        reset = 1;
        start = 0;
        master_tx_data = 8'b10100101; // Master -> Slave 전송 데이터
        slave_tx_data  = 8'b11001010; // Slave -> Master 전송 데이터

        #100;
        reset = 0;
        #100;

        // 통신 시작
        start = 1;
        wait(busy == 1);
        start = 0;

        // 통신 완료 대기
        wait(done == 1);
        #2000;

        $finish;
    end

endmodule
