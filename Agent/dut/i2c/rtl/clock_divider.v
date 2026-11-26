module clock_divider (
    input ck, // 50MHz
    input reset,

    output reg tick // SCL 1/4 주기마다 1 ck 펄스
);
    parameter CLK_FREQ = 50_000_000; // 50MHz
    parameter I2C_FREQ = 100_000; // 100kHz

    // SCL 한 주기를 4구간(SDA 변경, SCL 상승, SDA 샘플, SCL 하강)으로 나누기 위해 4배 속도로 tick 생성
    localparam DIV = CLK_FREQ / (I2C_FREQ * 4) - 1; // 124

    reg [6:0] count; // 2^7 = 128 > 124

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            count <= 0;
            tick  <= 0;
        end
        else if (count == DIV) begin
            count <= 0;
            tick  <= 1;
        end
        else begin
            count <= count + 1;
            tick  <= 0;
        end
    end
endmodule
