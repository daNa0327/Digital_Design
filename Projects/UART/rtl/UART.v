module UART(
    input  ck,
    input  reset,

    input  tx_start,
    input  [7:0] tx_data,
    output tx,
    output tx_busy,

    input  rx,
    output [7:0] rx_data,
    output data_valid
);
    wire baud_tick;

    Baud_Rate_Generator b1(
        .ck(ck),
        .reset(reset),

        .baud_tick(baud_tick)
    );

    UART_TX t1(
        .ck(ck),
        .reset(reset),
        .baud_tick(baud_tick),
        .tx_start(tx_start),
        .tx_data(tx_data),

        .tx(tx),
        .busy(tx_busy)
    );

    UART_RX r1(
        .ck(ck),
        .reset(reset),
        .baud_tick(baud_tick),
        .rx(rx),

        .data_valid(data_valid),
        .rx_data(rx_data)
    );

endmodule
