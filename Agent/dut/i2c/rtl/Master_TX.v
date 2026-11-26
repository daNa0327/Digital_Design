/*
Data[7]
  ↓
Data[6]
  ↓
...
  ↓
Data[0]
*/
module Master_TX (
    input ck,
    input reset,
    input load_addr,
    input load_data,
    input shift,
    input [6:0] addr,
    input rw,
    input [7:0] tx_data,

    output tx_bit
);
    reg [7:0] tx_reg;

    // MSB first: 항상 최상위 비트를 내보내고 SCL 하강마다 왼쪽으로 민다
    assign tx_bit = tx_reg[7];

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            tx_reg <= 8'b0;
        end
        else if (load_addr) begin
            tx_reg <= {addr, rw};       // 주소 7비트 + R/W
        end
        else if (load_data) begin
            tx_reg <= tx_data;
        end
        else if (shift) begin
            tx_reg <= {tx_reg[6:0], 1'b0};
        end
    end
endmodule
