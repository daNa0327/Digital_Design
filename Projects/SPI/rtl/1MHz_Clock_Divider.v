module clock_divider (
    input ck, // 50MHz
    input reset,

    output reg spi_clk
);
    parameter CLK_FREQ = 50_000_000; // 50MHz
    parameter SPI_FREQ = 1_000_000; // 1MHz

    localparam DIV = CLK_FREQ / (SPI_FREQ * 2) - 1;

    reg [4:0] count;   // 2^5 = 32 > 25

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            count    <= 0;
            spi_clk <= 0;
        end
        else if (count == DIV) begin
            count    <= 0;
            spi_clk <= ~spi_clk;
        end
        else begin
            count <= count + 1;
        end
    end

endmodule