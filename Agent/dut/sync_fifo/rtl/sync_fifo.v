module sync_fifo (
    input ck,
    input reset,

    input wr_en,
    input rd_en,

    input  [7:0] data_in,
    output [7:0] data_out,

    output full,
    output empty
);
    wire [2:0] wr_ptr;
    wire [2:0] rd_ptr;

    wire mem_wr_en;
    wire mem_rd_en;

    assign mem_wr_en = wr_en && !full;
    assign mem_rd_en = rd_en && !empty;

    fifo_ctrl c1 (
        .ck(ck),
        .reset(reset),

        .wr_en(mem_wr_en),
        .rd_en(mem_rd_en),

        .wr_ptr(wr_ptr),
        .rd_ptr(rd_ptr),

        .full(full),
        .empty(empty)
    );

    fifo_mem m1 (
        .ck(ck),

        .wr_en(mem_wr_en),
        .rd_en(mem_rd_en),

        .wr_addr(wr_ptr),
        .rd_addr(rd_ptr),

        .data_in(data_in),
        .data_out(data_out)
    );

endmodule