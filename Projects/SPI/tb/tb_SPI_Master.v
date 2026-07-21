`timescale 1ns/1ps

module SPI_Master_tb;

reg ck;
reg reset;
reg start;
reg [7:0] tx_data;

reg MISO;

wire spi_clk;
wire MOSI;
wire [7:0] rx_data;

wire CS;
wire load;
wire shift_en;
wire busy;
wire done;

SPI_Master dut(
    .ck(ck),
    .reset(reset),
    .start(start),
    .spi_clk(spi_clk),

    .tx_data(tx_data),
    .MOSI(MOSI),

    .MISO(MISO),
    .rx_data(rx_data),

    .CS(CS),
    .load(load),
    .shift_en(shift_en),
    .busy(busy),
    .done(done)
);

//////////////////////////////////////////////////////
// 50MHz Clock
//////////////////////////////////////////////////////

initial begin
    ck = 0;
    forever #10 ck = ~ck;
end

//////////////////////////////////////////////////////
// Test
//////////////////////////////////////////////////////

initial begin

    reset = 1;
    start = 0;
    tx_data = 8'b10100101;
    MISO = 0;

    #100;
    reset = 0;

    #100;

    start = 1;
    @(posedge spi_clk);
    start = 0;

end

//////////////////////////////////////////////////////
// Slave 역할
//////////////////////////////////////////////////////

reg [7:0] slave_data = 8'b11001010;
integer i;

initial begin
    MISO = 0;

    @(negedge CS);

    MISO = slave_data[7];

    @(posedge spi_clk);
    for (i = 6; i >= 0; i = i - 1) begin
        @(negedge spi_clk);
        MISO = slave_data[i];
    end

    @(negedge spi_clk);

    MISO = 0;
end

//////////////////////////////////////////////////////
// 종료
//////////////////////////////////////////////////////

initial begin

    #12_000;
    $finish;

end

endmodule