`timescale 1ns / 1ps

module sync_fifo_tb;
    reg ck;
    reg reset;

    reg wr_en;
    reg rd_en;

    reg  [7:0] data_in;
    wire [7:0] data_out;

    wire full;
    wire empty;

    // DUT
    sync_fifo dut (
        .ck(ck),
        .reset(reset),

        .wr_en(wr_en),
        .rd_en(rd_en),

        .data_in(data_in),
        .data_out(data_out),

        .full(full),
        .empty(empty)
    );

    // Clock 10ns
    always #5 ck = ~ck;

    initial begin
        // ======================
        // Reset
        // ======================
        ck      = 0;
        reset   = 0;
        wr_en   = 0;
        rd_en   = 0;
        data_in = 8'h00;
        #10; reset = 1;
        #10; reset = 0;


        // ======================
        // Write Test
        // 8개 데이터 저장
        // ======================
        #20;
        wr_en = 1;
        rd_en = 0;

             data_in = 8'h01;
        #10; data_in = 8'h02;
        #10; data_in = 8'h03;
        #10; data_in = 8'h04;
        #10; data_in = 8'h05;
        #10; data_in = 8'h06;
        #10; data_in = 8'h07;
        #10; data_in = 8'h08;
        #10; wr_en = 0;

        // ======================
        // Overflow Test
        // Full 상태 Write 무시
        // ======================
        #20;
        wr_en   = 1;

        #10; data_in = 8'h09;
        #10; data_in = 8'h0A;
        #10; wr_en = 0;

        // ======================
        // Read Test
        // 8개 데이터 출력
        // ======================
        #20;
        rd_en = 1;

        #10;
        #10;
        #10;
        #10;
        #10;
        #10;
        #10;
        #10; rd_en = 0;


        // ======================
        // Write + Read Test
        // ======================
        #20;
        // Write
        wr_en   = 1;
        rd_en   = 0;
        data_in = 8'hAA;

        #10;
        // 동시에 Write + Read
        wr_en   = 1;
        rd_en   = 1;
        data_in = 8'hBB;

        #10;
        // Read
        wr_en = 0;
        rd_en = 1;


        #50; $finish;
    end

endmodule
