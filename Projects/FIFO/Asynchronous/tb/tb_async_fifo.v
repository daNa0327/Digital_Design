`timescale 1ns / 1ps

module async_fifo_tb;

    reg wr_ck;
    reg rd_ck;
    reg reset;

    reg wr_en;
    reg rd_en;

    reg [7:0] data_in;
    wire [7:0] data_out;

    wire full;
    wire empty;

    // DUT
    async_fifo dut (
        .wr_ck(wr_ck),
        .rd_ck(rd_ck),
        .reset(reset),

        .wr_en(wr_en),
        .rd_en(rd_en),

        .data_in(data_in),
        .data_out(data_out),

        .full(full),
        .empty(empty)
    );

    // ======================
    // Clock
    // Write Clock : 10ns
    // Read Clock  : 14ns
    // ======================
    always #5 wr_ck = ~wr_ck;
    always #7 rd_ck = ~rd_ck;

    initial begin
        // ======================
        // Reset
        // ======================
        wr_ck   = 0;
        rd_ck   = 0;
        reset   = 0;
        wr_en   = 0;
        rd_en   = 0;
        data_in = 8'h00;
        #10; reset = 1;
        #10; reset = 0;


        // ======================
        // Write Test
        // FIFO 8개 데이터 저장
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


        // ======================
        // Overflow Test
        // Full 상태에서 Write
        // 무시되는지 확인
        // ======================
        #10; data_in = 8'h09;
        #10; data_in = 8'h0A;
        #10; wr_en = 0;


        // ======================
        // Read Test
        // 저장된 데이터 출력
        // ======================
        rd_en = 1;

        #14;
        #14;
        #14;
        #14;
        #14;
        #14;
        #14;
        #14; rd_en = 0;


        // ======================
        // Underflow Test
        // Empty 상태 Read
        // 무시되는지 확인
        // ======================
        #20; rd_en = 1;
        #50; rd_en = 0;


        // ======================
        // Write + Read Test
        // 서로 다른 Clock에서
        // 동시 동작
        // ======================
        // Write
        wr_en   = 1;
        rd_en   = 0;
        data_in = 8'hAA;

        #10;
        // Write + Read 동시 수행
        wr_en   = 1;
        rd_en   = 1;
        data_in = 8'hBB;

        #20;
        // Read
        wr_en = 0;
        rd_en = 1;


        #50; $finish;
    end

endmodule
