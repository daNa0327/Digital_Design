module SPI_RX ( // MISO로 들어오는 직렬 데이터를 SCLK에 맞춰 한 비트씩 받아서 8비트 병렬 데이터로 만드는 Shift Register
    input spi_clk,
    input reset,

    input shift_en, // shift_en = 1 shift 실행
    input MISO,

    output reg [7:0] rx_data
);
    always @(posedge spi_clk or posedge reset) begin
        if (reset) begin
            rx_data <= 8'b0;
        end
        else if (shift_en) begin
            rx_data <= {rx_data[6:0], MISO};
        end
    end
endmodule