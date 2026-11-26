module Master(
    input ck,
    input reset,
    input start,
    input rw,
    input [6:0] addr,

    input  [7:0] tx_data,
    output [7:0] rx_data,

    output SCL,
    input  sda_in,
    output sda_low,

    output busy,
    output done,
    output ack_error
);
    wire tick;
    wire tx_bit;
    wire load_addr;
    wire load_data;
    wire tx_shift;
    wire rx_shift;

    clock_divider c1 (
        .ck(ck),
        .reset(reset),
        .tick(tick)
    );

    Master_FSM f1 (
        .ck(ck),
        .reset(reset),
        .tick(tick),
        .start(start),
        .rw(rw),
        .tx_bit(tx_bit),
        .sda_in(sda_in),

        .SCL(SCL),
        .sda_low(sda_low),
        .load_addr(load_addr),
        .load_data(load_data),
        .tx_shift(tx_shift),
        .rx_shift(rx_shift),
        .busy(busy),
        .done(done),
        .ack_error(ack_error)
    );

    Master_TX t1 (
        .ck(ck),
        .reset(reset),
        .load_addr(load_addr),
        .load_data(load_data),
        .shift(tx_shift),
        .addr(addr),
        .rw(rw),
        .tx_data(tx_data),

        .tx_bit(tx_bit)
    );

    Master_RX r1 (
        .ck(ck),
        .reset(reset),
        .shift(rx_shift),
        .sda_in(sda_in),

        .rx_data(rx_data)
    );
endmodule
