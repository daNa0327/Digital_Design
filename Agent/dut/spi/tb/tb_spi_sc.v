// NOTE: 일부러 `timescale 지시문을 쓰지 않는다. 골든 RTL에는 timescale이 없고, xsim은 한 설계 안에서
//       timescale이 있는 모듈과 없는 모듈이 섞이면 xelab에서 XSIM 43-4099 에러를 낸다.
//       지시문이 없으면 xsim 기본값(1ns/1ps)이 적용되어 #10은 10ns, spi_clk 주기는 1000ns가 된다.
// Self-checking testbench for spi_system (SPI mode 0, 8-bit, Master+Slave 폐루프).
// 검증 방식: 블랙박스. 포트(spi_clk, CS, MOSI, MISO, busy, done, *_rx_data)만 명세와 비교한다.
//   1) 비트 모니터: spi_clk 상승 에지마다 CS=0이면 MOSI/MISO가 기대 비트(MSB first)인지, busy/done 상태가 맞는지
//   2) 전송 단위: 전송이 끝난 시점의 rx_data, 전송당 비트 수(8), 유휴 구간의 CS/busy/done/rx 유지
//   3) spi_clk 주기와 리셋 뒤 첫 에지 시각, 리셋 직후 상태, 데이터 선로가 spi_clk 하강 에지에서만 바뀌는지
// 자극: 비대칭 데이터, start가 spi_clk 어느 위상에서 들어오는 경우, done 중 start, start 유지(연속 전송), 전송 중 리셋.
// 로그 규약(Agent가 파싱): 마지막에 "[TB] PASS" 또는 "[TB] FAIL: ..." 한 줄만 출력한다.
//   불일치 상세는 "CHECK_FAIL ..." 줄로 최대 10개까지 출력한다.
module spi_sc_tb;
    reg        ck;
    reg        reset;
    reg        start;
    reg  [7:0] mtx;
    reg  [7:0] stx;
    wire [7:0] mrx;
    wire [7:0] srx;
    wire       spi_clk, CS, MOSI, MISO, busy, done;

    spi_system dut (
        .ck(ck), .reset(reset), .start(start),
        .master_tx_data(mtx), .slave_tx_data(stx),
        .master_rx_data(mrx), .slave_rx_data(srx),
        .spi_clk(spi_clk), .CS(CS), .MOSI(MOSI), .MISO(MISO),
        .busy(busy), .done(done)
    );

    always #10 ck = ~ck;                        // 50MHz, negedge: 10ns 간격으로 입력을 바꾼다

    // ------------------------------------------------------------
    // 판정 도우미
    // ------------------------------------------------------------
    integer errors, checks;
    integer bitn, pos_since_rst;                // check 태스크가 참조하므로 먼저 선언
    time    first_err_time;

    task check;
        input [8*24-1:0] what;                   // 24자: 가장 긴 이름(MOSI_change_at_rising, 21자)이 잘리지 않게
        input [31:0]  exp;
        input [31:0]  got;
        begin
            checks = checks + 1;
            if (exp !== got) begin
                if (errors == 0) first_err_time = $time;
                errors = errors + 1;
                if (errors <= 10)
                    $display("CHECK_FAIL t=%0t sig=%0s exp=%0h got=%0h (bit=%0d CS=%b busy=%b done=%b)",
                             $time, what, exp, got, bitn, CS, busy, done);
            end
        end
    endtask

    // ------------------------------------------------------------
    // 모니터: spi_clk 상승 에지 직전 값(DUT의 NBA 이전)을 본다
    // ------------------------------------------------------------
    reg [7:0] exp_m, exp_s;                     // 지금 전송에서 Master/Slave가 보낼 데이터
    reg       mon_en, expect_idle, in_xfer;
    reg [7:0] idle_m, idle_s;
    time      last_pos, t_rel;                  // t_rel: 리셋이 풀린 시각

    // 자극이 충분했는지 보기 위한 통계
    integer c_xfer, c_start_hi, c_start_lo, c_restart, c_held, c_midreset, c_idle;

    // 전송 중(CS=0) 데이터 선로는 spi_clk 하강 에지에서만 바뀐다 (mode 0). 상승 에지에서 바뀌면 샘플 시점과 겹친다.
    always @(MOSI) if (mon_en && CS === 1'b0 && spi_clk === 1'b1) check("MOSI_change_at_rising", 0, 1);
    always @(MISO) if (mon_en && CS === 1'b0 && spi_clk === 1'b1) check("MISO_change_at_rising", 0, 1);

    always @(posedge spi_clk) begin
        if (mon_en) begin
            if (pos_since_rst >= 1) check("spi_clk_period", 1000, $time - last_pos);
            else                    check("spi_clk_first_edge", 490, $time - t_rel);   // 리셋 해제 뒤 ck 25번째 상승 에지
            last_pos = $time;
            pos_since_rst = pos_since_rst + 1;
            if (CS === 1'b0) begin
                if (!in_xfer) begin in_xfer = 1; bitn = 0; end
                if (bitn < 8) begin
                    check("MOSI", exp_m[7 - bitn], MOSI);
                    check("MISO", exp_s[7 - bitn], MISO);
                    check("busy", (bitn >= 1), busy);        // 첫 샘플 에지에서 올라가므로 그 에지 직전엔 0
                    if (bitn >= 1) check("done", 0, done);
                end
                bitn = bitn + 1;
            end else begin
                if (in_xfer) begin
                    check("bit_count", 8, bitn);              // 전송당 정확히 8번
                    check("done", 1, done);                   // 마지막 샘플 에지에서 올라간 done
                    in_xfer = 0;
                end
                if (expect_idle) begin
                    c_idle = c_idle + 1;
                    check("CS", 1, CS);
                    check("busy", 0, busy);
                    check("done", 0, done);
                    check("master_rx_hold", idle_m, mrx);
                    check("slave_rx_hold", idle_s, srx);
                end
            end
        end
    end

    // ------------------------------------------------------------
    // 자극 도우미: 모든 입력은 negedge ck에서 바꾼다
    // ------------------------------------------------------------
    integer g;

    task wait_busy;
        begin
            g = 0;
            while (busy !== 1'b1 && g < 400) begin @(posedge ck); g = g + 1; end
            if (g >= 400) check("busy_rise_timeout", 1, 0);
        end
    endtask

    task wait_done_high;
        begin
            g = 0;
            while (done !== 1'b1 && g < 600) begin @(posedge ck); g = g + 1; end
            if (g >= 600) check("done_rise_timeout", 1, 0);
        end
    endtask

    task wait_done_low;
        begin
            g = 0;
            while (done !== 1'b0 && g < 400) begin @(posedge ck); g = g + 1; end
            if (g >= 400) check("done_fall_timeout", 0, 1);
        end
    endtask

    task set_data;
        input [7:0] m;
        input [7:0] s;
        begin
            mtx = m; stx = s; exp_m = m; exp_s = s;
        end
    endtask

    task assert_start;                           // start를 올리고 busy가 오를 때까지 유지한 뒤 내린다
        begin
            expect_idle = 0;
            @(negedge ck);
            if (spi_clk) c_start_hi = c_start_hi + 1; else c_start_lo = c_start_lo + 1;
            start = 1;
            wait_busy;
            start = 0;
        end
    endtask

    task check_final;                            // done이 오른 직후: 받은 데이터
        begin
            wait_done_high;
            #2;
            check("master_rx_data", exp_s, mrx);
            check("slave_rx_data",  exp_m, srx);
            c_xfer = c_xfer + 1;
        end
    endtask

    task go_idle;                                // done이 내려간 뒤 유휴 상태로 두고 유휴 검사를 켠다
        input integer cycles;
        begin
            wait_done_low;
            repeat (4) @(negedge ck);
            idle_m = mrx; idle_s = srx;
            expect_idle = 1;
            repeat (cycles) @(negedge ck);
        end
    endtask

    task xfer;                                   // 일반 전송 1회. pre: 시작 전 대기 ck 사이클 수 (spi_clk 위상 이동용)
        input [7:0] m;
        input [7:0] s;
        input integer pre;
        begin
            set_data(m, s);
            repeat (pre) @(negedge ck);
            assert_start;
            check_final;
            go_idle(0);
        end
    endtask

    task xfer_restart;                           // done이 1인 동안 다음 start (이전 전송 직후 바로 연속)
        input [7:0] m1;
        input [7:0] s1;
        input [7:0] m2;
        input [7:0] s2;
        begin
            set_data(m1, s1);
            assert_start;
            check_final;                         // 지금 done=1 구간
            c_restart = c_restart + 1;
            set_data(m2, s2);
            assert_start;
            check_final;
            go_idle(0);
        end
    endtask

    task xfer_held;                              // start를 계속 1로 둔 연속 전송 n회 (같은 데이터)
        input [7:0] m;
        input [7:0] s;
        input integer n;
        integer j;
        begin
            set_data(m, s);
            expect_idle = 0;
            @(negedge ck);
            start = 1;
            for (j = 0; j < n; j = j + 1) begin
                check_final;
                c_held = c_held + 1;
                wait_done_low;                   // 이 시점에 다음 전송이 시작된 상태 (마지막 반복의 다음 전송은 아래에서 마무리)
            end
            start = 0;
            wait_done_high;                      // 마지막으로 시작된 전송도 끝까지 본다
            #2;
            check("master_rx_data", exp_s, mrx);
            check("slave_rx_data",  exp_m, srx);
            go_idle(0);
        end
    endtask

    task do_reset;                               // 비동기 리셋 5 ck 사이클. 리셋 직후 상태를 확인한다
        begin
            mon_en = 0; expect_idle = 0; in_xfer = 0;
            reset = 1;
            #1;
            check("CS_reset", 1, CS);
            check("busy_reset", 0, busy);
            check("done_reset", 0, done);
            check("master_rx_reset", 0, mrx);
            check("slave_rx_reset", 0, srx);
            check("spi_clk_reset", 0, spi_clk);
            repeat (5) @(negedge ck);
            reset = 0;
            t_rel = $time;
            bitn = 0; pos_since_rst = 0; last_pos = 0;
            mon_en = 1;
            idle_m = 0; idle_s = 0;
        end
    endtask

    task xfer_midreset;                          // 전송 도중 리셋 (npos번째 상승 에지 이후, 에지에서 off ns 뒤)
        input [7:0] m;
        input [7:0] s;
        input integer npos;
        input integer off;
        begin
            set_data(m, s);
            assert_start;
            repeat (npos) @(posedge spi_clk);
            #(off);
            c_midreset = c_midreset + 1;
            do_reset;
            go_idle(40);
            xfer(8'hB1, 8'h6C, 0);               // 리셋 뒤에도 정상 전송
        end
    endtask

    // ------------------------------------------------------------
    // 시나리오
    // ------------------------------------------------------------
    integer i, k, seed;
    reg [7:0] rm, rs;

    task report;
        begin
            $display("COVER xfer=%0d start_spi_clk_high=%0d start_spi_clk_low=%0d restart_in_done=%0d held=%0d midreset=%0d idle_checks=%0d",
                     c_xfer, c_start_hi, c_start_lo, c_restart, c_held, c_midreset, c_idle);
            $display("CHECKS total=%0d mismatches=%0d", checks, errors);
            if (errors == 0)
                $display("[TB] PASS");
            else
                $display("[TB] FAIL: %0d mismatches, first at %0t", errors, first_err_time);
        end
    endtask

    initial begin                                // 시간 초과 감시 (DUT가 멈춰도 로그를 남긴다)
        #3_000_000;                            // 3ms: 골든 종료(약 0.89ms)의 3배 이상. 멈춘 DUT에서 xsim 실행 시간이 길어지지 않게 한다
        check("tb_timeout", 0, 1);
        report;
        $finish;
    end

    initial begin
        ck = 0; reset = 0; start = 0; mtx = 8'h00; stx = 8'h00; exp_m = 0; exp_s = 0;
        errors = 0; checks = 0; first_err_time = 0;
        mon_en = 0; expect_idle = 0; in_xfer = 0; idle_m = 0; idle_s = 0; bitn = 0; pos_since_rst = 0; last_pos = 0; t_rel = 0;
        c_xfer = 0; c_start_hi = 0; c_start_lo = 0; c_restart = 0; c_held = 0; c_midreset = 0; c_idle = 0;
        seed = 32'h1357_9BDF;
        $timeformat(-9, 0, " ns", 0);

        // 1) 리셋 + 유휴 구간 (spi_clk 3주기 이상): CS=1, busy=0, done=0, rx 유지
        #3;
        do_reset;
        go_idle(160);

        // 2) 비대칭 데이터 방향별 확인 (MSB first, Master/Slave 방향 구분)
        xfer(8'hB1, 8'h6C, 0);
        xfer(8'h80, 8'h01, 0);
        xfer(8'h01, 8'h80, 0);
        xfer(8'hF0, 8'h0F, 0);
        xfer(8'h3D, 8'hE2, 0);
        xfer(8'hFF, 8'h00, 0);
        xfer(8'h00, 8'hFF, 0);
        xfer(8'hA5, 8'h5A, 0);

        // 3) start가 spi_clk 모든 위상에서 들어오는 경우 (50 ck 사이클 = spi_clk 1주기)
        for (k = 0; k < 50; k = k + 3) begin
            rm = {$random(seed)} % 256;
            rs = {$random(seed)} % 256;
            xfer(rm, rs, k);
        end

        // 4) done 구간에 start (연속 전송)
        xfer_restart(8'hA6, 8'h3C, 8'hB1, 8'h6C);
        xfer_restart(8'h12, 8'hED, 8'h87, 8'h78);

        // 5) start 유지: 연속으로 3회 반복
        xfer_held(8'h91, 8'h5A, 3);

        // 6) 전송 중 리셋 (초반, 중반, 후반) 후 정상 동작
        xfer_midreset(8'hC5, 8'h96, 1, 137);
        xfer_midreset(8'hC5, 8'h96, 4, 300);
        xfer_midreset(8'hC5, 8'h96, 7, 61);

        // 7) 데이터가 있는 상태에서 리셋: rx 지워짐, 이후 정상
        xfer(8'h4E, 8'hA9, 0);
        do_reset;
        go_idle(60);
        xfer(8'h4E, 8'hA9, 5);

        // 8) 랜덤 전송 (고정 seed, 결정적): 위상 무작위, 가끔 연속 전송과 리셋
        for (i = 0; i < 40; i = i + 1) begin
            rm = {$random(seed)} % 256;
            rs = {$random(seed)} % 256;
            case ({$random(seed)} % 8)
                0: xfer_restart(rm, rs, ~rm, ~rs);
                1: begin do_reset; go_idle(30); xfer(rm, rs, {$random(seed)} % 60); end
                default: xfer(rm, rs, {$random(seed)} % 120);
            endcase
        end

        go_idle(100);
        report;
        $finish;
    end
endmodule