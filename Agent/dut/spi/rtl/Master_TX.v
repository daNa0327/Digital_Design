module Master_TX (
    input spi_clk,
    input reset,
    input CS,
    input [7:0] tx_data, 

    output MOSI
);
    reg [2:0] bit_cnt;

    // CS가 1일 때는 무조건 tx_data[7] (MSB)을 미리 선로에 올려둠
    // CS가 0일 때는 negedge마다 증가하는 bit_cnt에 맞춰 비트 출력
    assign MOSI = tx_data[3'd7 - bit_cnt];

    always @(negedge spi_clk or posedge CS or posedge reset) begin
        if (reset) begin
            bit_cnt <= 3'b0;
        end
        else if (CS) begin
            // CS=1 (대기 상태) 일 때 카운터 리셋
            bit_cnt <= 3'b0;
        end
        else begin
            // CS=0 (전송 상태) 일 때 negedge 마다 다음 비트로 이동
            bit_cnt <= bit_cnt + 1'b1;
        end
    end
endmodule
