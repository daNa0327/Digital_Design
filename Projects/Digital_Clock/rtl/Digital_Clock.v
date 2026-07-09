module Digital_Clock (
    input ck,
    input reset,

    output [3:0] h_t,
    output [3:0] h_o,
    output [3:0] m_t,
    output [3:0] m_o,
    output [3:0] s_t,
    output [3:0] s_o
);
    wire clk_1hz;
    clock_divider c1(
        .ck(ck),
        .reset(reset),
        .clk_1hz(clk_1hz)
    );

    wire [5:0] sec;
    wire sec_carry;
    sec_counter s1(
        .ck(clk_1hz),
        .reset(reset),
        .sec(sec),
        .carry(sec_carry)
    );

    wire [5:0] min;
    wire min_carry;
    min_counter m1(
        .ck(clk_1hz),
        .reset(reset),
        .sec_carry(sec_carry),
        .min(min),
        .carry(min_carry)
    );

    wire [4:0] hour;
    hour_counter h1(
        .ck(clk_1hz),
        .reset(reset),
        .min_carry(min_carry),
        .hour(hour)
    );

    assign h_t = hour / 10;
    assign h_o = hour % 10;
    assign m_t = min / 10;
    assign m_o = min % 10;
    assign s_t = sec / 10;
    assign s_o = sec % 10;
endmodule
