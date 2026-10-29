`timescale 1ns / 1ps

module async_fifo (
    input wr_ck,
    input rd_ck,
    input reset,

    input wr_en,
    input rd_en,

    input  [7:0] data_in,
    output [7:0] data_out,

    output full,
    output empty
);
    wire [3:0] wr_ptr;
    wire [3:0] rd_ptr;

    wire mem_wr_en;
    wire mem_rd_en;

    assign mem_wr_en = wr_en && !full;
    assign mem_rd_en = rd_en && !empty;

    fifo_ctrl c1 (
        .wr_ck(wr_ck),
        .rd_ck(rd_ck),
        .reset(reset),

        .wr_en(mem_wr_en),
        .rd_en(mem_rd_en),

        .wr_ptr(wr_ptr),
        .rd_ptr(rd_ptr),

        .full(full),
        .empty(empty)
    );

    fifo_mem m1 (
        .wr_ck(wr_ck),
        .rd_ck(rd_ck),

        .wr_en(mem_wr_en),
        .rd_en(mem_rd_en),

        .wr_addr(wr_ptr[2:0]),
        .rd_addr(rd_ptr[2:0]),

        .data_in(data_in),
        .data_out(data_out)
    );
endmodule
