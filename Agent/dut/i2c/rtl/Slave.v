module Slave(
    input ck,
    input reset,
    input SCL,
    input sda_in,
    output sda_low,

    input  [7:0] tx_data,
    output [7:0] rx_data
);
    wire [7:0] rx_shreg;
    wire tx_bit;
    wire rx_shift;
    wire rx_latch;
    wire tx_load;
    wire tx_shift;

    Slave_FSM f1 (
        .ck(ck),
        .reset(reset),
        .SCL(SCL),
        .sda_in(sda_in),
        .rx_shreg(rx_shreg),
        .tx_bit(tx_bit),

        .sda_low(sda_low),
        .rx_shift(rx_shift),
        .rx_latch(rx_latch),
        .tx_load(tx_load),
        .tx_shift(tx_shift)
    );

    Slave_TX t1 (
        .ck(ck),
        .reset(reset),
        .load(tx_load),
        .shift(tx_shift),
        .tx_data(tx_data),

        .tx_bit(tx_bit)
    );

    Slave_RX r1 (
        .ck(ck),
        .reset(reset),
        .shift(rx_shift),
        .latch(rx_latch),
        .sda_in(sda_in),

        .rx_shreg(rx_shreg),
        .rx_data(rx_data)
    );
endmodule
