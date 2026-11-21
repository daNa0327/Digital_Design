// NOTE: 일부러 `timescale 지시문을 쓰지 않는다. 골든 RTL에는 timescale이 없고, xsim은 한 설계 안에서
//       timescale이 있는 모듈과 없는 모듈이 섞이면 xelab에서 XSIM 43-4099 에러를 낸다.
//       지시문이 없으면 xsim 기본값(1ns/1ps)이 적용되어 #5는 5ns, VCD는 1ps 해상도가 된다.
// Self-checking testbench for sync_fifo (depth 8, 8-bit, synchronous read).
// 검증 방식: 블랙박스 비교. 포트(full/empty/data_out)만 참조 모델과 비교한다.
// 로그 규약(Agent가 파싱): 마지막에 "[TB] PASS" 또는 "[TB] FAIL: ..." 한 줄만 출력한다.
//   불일치 상세는 "CHECK_FAIL ..." 줄로 최대 10개까지 출력한다.
module sync_fifo_sc_tb;
    localparam DEPTH = 8;

    reg        ck;
    reg        reset;
    reg        wr_en;
    reg        rd_en;
    reg  [7:0] data_in;
    wire [7:0] data_out;
    wire       full;
    wire       empty;

    sync_fifo dut (
        .ck(ck), .reset(reset),
        .wr_en(wr_en), .rd_en(rd_en),
        .data_in(data_in), .data_out(data_out),
        .full(full), .empty(empty)
    );

    always #5 ck = ~ck;                         // 10ns clock, posedge: 5, 15, 25 ...

    // ------------------------------------------------------------
    // Reference model (명세 기준)
    //  - 깊이 8, full에서 write 무시, empty에서 read 무시
    //  - 동시 write+read: empty면 write만, full이면 read만, 그 외는 둘 다
    //  - read data는 클럭 에지에서 갱신되어 다음 사이클에 보임 (동기 읽기)
    //  - data_out은 reset으로 지워지지 않고, read가 없으면 값을 유지
    // ------------------------------------------------------------
    reg [7:0] m_mem [0:DEPTH-1];
    reg [2:0] m_wr, m_rd;
    integer   m_count;
    reg [7:0] m_dout;
    reg       m_dout_valid;
    reg       do_wr, do_rd;

    // 자극이 충분했는지 보기 위한 통계
    integer c_full, c_empty, c_over, c_under, c_both_full, c_both_empty, c_wrap, c_reset;

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            m_wr = 0; m_rd = 0; m_count = 0;
            c_reset = c_reset + 1;
        end else begin
            do_wr = wr_en && (m_count != DEPTH);
            do_rd = rd_en && (m_count != 0);
            if (wr_en && m_count == DEPTH) c_over  = c_over  + 1;
            if (rd_en && m_count == 0)     c_under = c_under + 1;
            if (wr_en && rd_en && m_count == DEPTH) c_both_full  = c_both_full  + 1;
            if (wr_en && rd_en && m_count == 0)     c_both_empty = c_both_empty + 1;
            if (do_rd) begin                    // read는 write 이전 값을 읽는다
                m_dout = m_mem[m_rd];
                m_dout_valid = 1;
                m_rd = m_rd + 1;
            end
            if (do_wr) begin
                m_mem[m_wr] = data_in;
                if (m_wr == DEPTH-1) c_wrap = c_wrap + 1;
                m_wr = m_wr + 1;
            end
            m_count = m_count + do_wr - do_rd;
            if (m_count == DEPTH) c_full  = c_full  + 1;
            if (m_count == 0)     c_empty = c_empty + 1;
        end
    end

    // ------------------------------------------------------------
    // Checker: 매 posedge 2ns 뒤(입력이 negedge에서 바뀌므로 경쟁 없음)
    // ------------------------------------------------------------
    reg     check_en;
    integer errors, checks;
    time    first_err_time;

    task mismatch;
        input [79:0] what;
        input [7:0]  exp;
        input [7:0]  got;
        begin
            if (errors == 0) first_err_time = $time;
            errors = errors + 1;
            if (errors <= 10)
                $display("CHECK_FAIL t=%0t sig=%0s exp=%0h got=%0h (model_count=%0d wr_en=%b rd_en=%b)",
                         $time, what, exp, got, m_count, wr_en, rd_en);
        end
    endtask

    always @(posedge ck) begin
        #2;
        if (check_en) begin
            checks = checks + 1;
            if (full  !== (m_count == DEPTH)) mismatch("full",  (m_count == DEPTH), full);
            if (empty !== (m_count == 0))     mismatch("empty", (m_count == 0),     empty);
            if (m_dout_valid && (data_out !== m_dout)) mismatch("data_out", m_dout, data_out);
        end
    end

    // ------------------------------------------------------------
    // Stimulus helpers: 모든 입력은 negedge에서 바꾼다
    // ------------------------------------------------------------
    integer i, ph, n, wp, rp;
    integer seed;

    task drive;                                  // 한 사이클 동안 입력 유지
        input w; input r; input [7:0] d;
        begin
            @(negedge ck);
            wr_en = w; rd_en = r; data_in = d;
        end
    endtask

    task do_reset;                               // 한 사이클 리셋
        begin
            @(negedge ck);
            reset = 1; wr_en = 0; rd_en = 0;
            @(negedge ck);
            reset = 0;
            check_en = 1;
        end
    endtask

    initial begin
        ck = 0; reset = 0; wr_en = 0; rd_en = 0; data_in = 8'h00;
        check_en = 0; errors = 0; checks = 0; first_err_time = 0;
        m_wr = 0; m_rd = 0; m_count = 0; m_dout = 0; m_dout_valid = 0;
        c_full = 0; c_empty = 0; c_over = 0; c_under = 0;
        c_both_full = 0; c_both_empty = 0; c_wrap = 0; c_reset = 0;
        seed = 32'h1234_5678;
        $timeformat(-9, 0, " ns", 0);

        // 1) 리셋
        do_reset;

        // 2) 8개 채우기 + overflow 3회 (full에서 write 무시)
        for (i = 1; i <= 8; i = i + 1) drive(1, 0, i[7:0]);
        for (i = 9; i <= 11; i = i + 1) drive(1, 0, i[7:0]);
        drive(0, 0, 8'h00);

        // 3) 8개 읽기 + underflow 3회 (empty에서 read 무시, data_out 유지)
        for (i = 0; i < 8; i = i + 1) drive(0, 1, 8'h00);
        for (i = 0; i < 3; i = i + 1) drive(0, 1, 8'h00);
        drive(0, 0, 8'h00);

        // 4) empty에서 동시 write+read (write만 수행되어야 함)
        drive(1, 1, 8'hAA);
        drive(1, 1, 8'hBB);                      // 이제 1개 있음: 둘 다 수행
        drive(1, 1, 8'hCC);
        drive(0, 0, 8'h00);

        // 5) full에서 동시 write+read (read만 수행되어야 함)
        for (i = 0; i < 8; i = i + 1) drive(1, 0, 8'h50 + i[7:0]);
        drive(1, 1, 8'hDD);
        drive(1, 1, 8'hEE);
        drive(0, 1, 8'h00);
        drive(0, 0, 8'h00);

        // 6) 포인터 랩어라운드: 5개 채운 뒤 동시 write+read 24사이클
        do_reset;
        for (i = 0; i < 5; i = i + 1) drive(1, 0, 8'h60 + i[7:0]);
        for (i = 0; i < 24; i = i + 1) drive(1, 1, 8'h80 + i[7:0]);
        for (i = 0; i < 6; i = i + 1) drive(0, 1, 8'h00);

        // 7) 데이터가 있는 상태에서 리셋 -> empty, 이후 정상 동작
        for (i = 0; i < 3; i = i + 1) drive(1, 0, 8'hA0 + i[7:0]);
        do_reset;
        drive(0, 1, 8'h00);                      // 리셋 직후 read 시도(무시)
        drive(1, 0, 8'h5A);
        drive(0, 1, 8'h00);
        drive(0, 0, 8'h00);

        // 8) 랜덤 4구간 (고정 seed, 결정적): write 우세 / read 우세 / 균등 / 양쪽 높음 + 가끔 리셋
        for (ph = 0; ph < 4; ph = ph + 1) begin
            case (ph)
                0: begin wp = 6; rp = 2; end
                1: begin wp = 2; rp = 6; end
                2: begin wp = 4; rp = 4; end
                default: begin wp = 7; rp = 7; end
            endcase
            for (n = 0; n < 1000; n = n + 1) begin
                if (ph == 3 && ({$random(seed)} % 200) == 0) begin
                    do_reset;
                end else begin
                    drive((({$random(seed)} % 8) < wp), (({$random(seed)} % 8) < rp), $random(seed));
                end
            end
        end

        // 마무리
        drive(0, 0, 8'h00);
        repeat (3) @(negedge ck);

        $display("COVER full=%0d empty=%0d overflow=%0d underflow=%0d both_at_full=%0d both_at_empty=%0d wrap=%0d reset=%0d",
                 c_full, c_empty, c_over, c_under, c_both_full, c_both_empty, c_wrap, c_reset);
        $display("CHECKS total=%0d mismatches=%0d", checks, errors);
        if (errors == 0)
            $display("[TB] PASS");
        else
            $display("[TB] FAIL: %0d mismatches, first at %0t", errors, first_err_time);
        $finish;
    end
endmodule