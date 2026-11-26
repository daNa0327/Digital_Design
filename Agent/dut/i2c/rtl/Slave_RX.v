module Slave_RX (
    input ck,
    input reset,
    input shift,
    input latch,
    input sda_in,

    output reg [7:0] rx_shreg,  // 수신 중인 비트 (주소 비교에도 사용)
    output reg [7:0] rx_data    // 쓰기 데이터 수신이 끝났을 때만 갱신
);
    always @(posedge ck or posedge reset) begin
        if (reset) begin
            rx_shreg <= 8'b0;
            rx_data  <= 8'b0;
        end
        else begin
            if (shift)
                rx_shreg <= {rx_shreg[6:0], sda_in};
            if (latch)
                rx_data <= rx_shreg;
        end
    end
endmodule
