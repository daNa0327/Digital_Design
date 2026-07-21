module SPI_TX (
    input spi_clk,
    input reset,

    input load,
    input shift_en,
    input [7:0] tx_data, 

    output MOSI
);
    reg [7:0] shift_data;

    assign MOSI = shift_data[7];

    always @(negedge spi_clk or posedge reset) begin
        if (reset) begin
            shift_data <= 8'b0;
        end
        else if (load) begin
            shift_data <= tx_data;
        end
        else if (shift_en) begin
            shift_data <= {shift_data[6:0], 1'b0};
        end
    end
endmodule
