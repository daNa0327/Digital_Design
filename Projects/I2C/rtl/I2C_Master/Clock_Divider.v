module clock_divider (
    input ck, // 50MHz
    input reset,

    output reg SCL // Serial Clock
);
    parameter CLK_FREQ = 50_000_000; // 50MHz
    parameter I2C_FREQ = 100_000; // 100kHz

    localparam DIV = CLK_FREQ / (I2C_FREQ * 2) - 1;

    reg [7:0] count; // 2^8 = 256 > 250

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            count <= 0;
            SCL   <= 1;
        end
        else if (count == DIV) begin
            count <= 0;
            SCL   <= ~SCL;
        end
        else begin
            count <= count + 1;
        end
    end
endmodule
