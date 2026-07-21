module SPI_TX ( // 보낼 데이터를 저장하고, SCLK에 맞춰 한 비트씩 MOSI로 내보내는 Shift Register
    input spi_clk,
    input reset,

    input load, // load = 1 데이터 저장
    input shift_en, // shift_en = 1 shift 실행
    input [7:0] tx_data, 

    output MOSI
);
    reg [7:0] shift_data;

    assign MOSI = shift_data[7];

    always @(posedge spi_clk or posedge reset) begin
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
