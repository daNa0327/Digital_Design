// NOTE: 일부러 `timescale 지시문을 쓰지 않는다 (골든 RTL에 없고, xsim은 섞이면 XSIM 43-4099 에러).
//       지시문이 없으면 xsim 기본값(1ns/1ps)이 적용되어 #10은 10ns, ck 주기는 20ns가 된다.
// Self-checking testbench for UART (8N1, LSB first, 50MHz / 115200bps -> 1비트 = ck 434주기).
// 검증 방식: 블랙박스. 포트(tx, tx_busy, rx_data, data_valid)만 명세(dut/uart/spec.md)와 비교한다.
//   TX: tx_start 수락 시점과 start 비트 시작 에지, 각 비트 중앙의 tx 값과 tx_busy, busy 하강 에지,
//       tx/tx_busy가 baud tick 에지에서만 바뀌는지, 전송 중 tx_start 무시, 래치 후 tx_data 변경 무시
//   RX: data_valid 시점(start 하강 감지 후 4123 ck)과 1주기 펄스, rx_data 값과 유지, 프레임당 펄스 1개,
//       stop 비트가 0이면 data_valid 없음, TB 비트 주기 ±2%에서도 정상 수신
//   공통: 리셋 직후 상태, 전송/수신 중 리셋, TX와 RX 동시 동작, tx를 rx로 되돌린 루프백
// 로그 규약(Agent가 파싱): 불일치는 "CHECK_FAIL ..." 줄로 최대 10개, 마지막에 "[TB] PASS" 또는 "[TB] FAIL: ..." 한 줄.
module uart_sc_tb;
    reg        ck;
    reg        reset;
    reg        tx_start;
    reg  [7:0] tx_data;
    reg        rx_drv;
    reg        loop;
    wire       tx, tx_busy, data_valid;
    wire [7:0] rx_data;
    wire       rx = loop ? tx : rx_drv;

    UART dut (
        .ck(ck), .reset(reset),
        .tx_start(tx_start), .tx_data(tx_data), .tx(tx), .tx_busy(tx_busy),
        .rx(rx), .rx_data(rx_data), .data_valid(data_valid)
    );

    always #10 ck = ~ck;                        // 50MHz. 입력은 negedge에서 바꾼다

    localparam BIT   = 434;                     // 1비트 = ck 434주기 (50_000_000 / 115200 = 434)
    localparam VALID = 4123;                    // start 하강을 처음 본 에지부터 data_valid 에지까지 (9.5비트)

    // ------------------------------------------------------------
    // 판정 도우미 (check 태스크가 참조하는 변수는 먼저 선언: xsim은 선언 순서를 엄격히 본다)
    // ------------------------------------------------------------
    integer errors, checks;
    integer cyc;                                // 리셋 해제 후 ck 상승 에지 수 (리셋 중 0)
    time    first_err_time;

    task check;
        input [8*24-1:0] what;                  // 24자: 가장 긴 이름이 잘리지 않게
        input [31:0]     exp;
        input [31:0]     got;
        begin
            checks = checks + 1;
            if (exp !== got) begin
                if (errors == 0) first_err_time = $time;
                errors = errors + 1;
                if (errors <= 10)
                    $display("CHECK_FAIL t=%0t sig=%0s exp=%0h got=%0h (cyc=%0d tx=%b tx_busy=%b data_valid=%b rx_data=%h)",
                             $time, what, exp, got, cyc, tx, tx_busy, data_valid, rx_data);
            end
        end
    endtask

    always @(posedge ck or posedge reset)
        if (reset) cyc <= 0;
        else       cyc <= cyc + 1;

    // baud tick 에지: 리셋 해제 후 435, 869, ... 번째 상승 에지 (cyc % BIT == 1, cyc > 1)
    function is_tick;
        input integer n;
        is_tick = (n > 1) && (n % BIT == 1);
    endfunction

    // tx, tx_busy는 tick 에지에서만 바뀐다 (리셋에 의한 변화는 제외)
    reg mon_tick;
    always @(tx or tx_busy) begin
        #1;
        if (mon_tick && !reset && cyc > 0)
            check("tx_change_off_tick", 1, is_tick(cyc));
    end

    // data_valid 펄스 수 (프레임당 1개인지 비교)
    integer n_valid;
    always @(posedge ck) begin
        #1;
        if (!reset && data_valid) n_valid = n_valid + 1;
    end

    // 커버리지 카운터
    integer c_tx, c_rx, c_tol, c_ferr, c_held, c_ignored, c_midreset, c_loop, c_duplex;

    // ------------------------------------------------------------
    // 자극 / 검사 태스크
    // ------------------------------------------------------------
    task do_reset;                              // 비동기 리셋 5 ck. 리셋 중 상태를 확인한다
        begin
            @(negedge ck);
            reset = 1; tx_start = 0; rx_drv = 1;
            #1;
            check("tx_reset", 1, tx);
            check("tx_busy_reset", 0, tx_busy);
            check("data_valid_reset", 0, data_valid);
            check("rx_data_reset", 0, rx_data);
            repeat (5) @(negedge ck);
            reset = 0;
        end
    endtask

    task wait_cyc;                              // cyc가 n이 된 에지 직후(+1ns)까지 기다린다
        input integer n;
        begin
            #0;                                 // cyc는 NBA로 바뀌므로 에지 직후가 아니라 #1 뒤에 읽는다
            while (cyc < n) begin @(posedge ck); #1; end
        end
    endtask

    integer t_s, t_a, t_e, t_i;
    reg [7:0] t_d;
    task tx_frame;                              // tx_start를 tx_busy가 오를 때까지 유지. hold=1이면 내리지 않는다. bits=0이면 비트 검사 생략
        input [7:0] d;
        input integer hold;
        input integer bits;
        begin
            @(negedge ck);
            t_d = d;
            tx_data = d; tx_start = 1;
            t_s = cyc;
            t_a = t_s + 1;                      // 수락 에지: tx_start를 본 첫 tick 에지
            while (!is_tick(t_a)) t_a = t_a + 1;
            t_e = t_a + BIT;                    // start 비트 시작 에지
            wait_cyc(t_e - 1);
            check("tx_busy_before_start", 0, tx_busy);
            check("tx_before_start", 1, tx);
            wait_cyc(t_e);
            check("tx_start_bit_edge", 0, tx);
            check("tx_busy_rise", 1, tx_busy);
            if (!hold) begin
                @(negedge ck);
                tx_start = 0;
                tx_data = ~d;                   // 래치 이후 tx_data가 바뀌어도 프레임에는 영향이 없어야 한다
            end
            if (bits) tx_check_bits(t_e, t_d);
            c_tx = c_tx + 1;
        end
    endtask

    task tx_check_bits;                         // e: start 비트 시작 에지. 각 비트 중앙에서 tx와 tx_busy
        input integer e;
        input [7:0]   d;
        begin
            wait_cyc(e + BIT/2);
            check("tx_start_bit", 0, tx);
            for (t_i = 0; t_i < 8; t_i = t_i + 1) begin
                wait_cyc(e + BIT*(t_i + 1) + BIT/2);
                check("tx_data_bit", d[t_i], tx);
                check("tx_busy", 1, tx_busy);
            end
            wait_cyc(e + BIT*9 + BIT/2);
            check("tx_stop_bit", 1, tx);
            check("tx_busy", 1, tx_busy);
        end
    endtask

    task tx_end;                                // 마지막 프레임 뒤: stop 비트가 끝나는 에지에서 busy 하강, 2비트 동안 유휴
        input integer e;
        begin
            wait_cyc(e + BIT*10 - 1);
            check("tx_busy_fall", 1, tx_busy);
            wait_cyc(e + BIT*10);
            check("tx_busy_fall", 0, tx_busy);
            wait_cyc(e + BIT*12);
            check("tx_idle_high", 1, tx);
            check("tx_idle_busy", 0, tx_busy);
        end
    endtask

    integer r_f, r_i, r_k, r_nv;
    reg [7:0] r_last;
    task rx_frame;                              // rx_drv로 8N1 프레임. blen: TB 비트 주기(ck), stop: stop 비트 값
        input [7:0]   d;
        input integer blen;
        input         stop;
        begin
            @(negedge ck);
            check("rx_data_hold", r_last, rx_data);
            r_nv = n_valid;
            rx_drv = 0;                         // start 비트
            r_f = cyc + 1;                      // DUT가 하강을 처음 보는 에지
            repeat (blen) @(negedge ck);
            for (r_i = 0; r_i < 8; r_i = r_i + 1) begin
                rx_drv = d[r_i];
                repeat (blen) @(negedge ck);
            end
            rx_drv = stop;
            if (stop) begin
                wait_cyc(r_f + VALID - 1);
                check("data_valid_early", 0, data_valid);
                wait_cyc(r_f + VALID);
                check("data_valid", 1, data_valid);
                check("rx_data", d, rx_data);
                wait_cyc(r_f + VALID + 1);
                check("data_valid_pulse", 0, data_valid);
                r_last = d;
                c_rx = c_rx + 1;
            end else begin                      // stop 비트 0: 샘플 에지 직후 1로 되돌려 새 start로 오인하지 않게 한다
                wait_cyc(r_f + VALID);
                @(negedge ck);
                rx_drv = 1;
                c_ferr = c_ferr + 1;
            end
            repeat (blen) @(negedge ck);        // stop 비트 뒤 유휴 1비트
            check("data_valid_count", r_nv + (stop ? 1 : 0), n_valid);
            check("rx_data_hold", r_last, rx_data);
        end
    endtask

    integer k, seed, e0;
    reg [7:0] rd;

    task report;
        begin
            $display("COVER tx=%0d rx=%0d rx_tol=%0d frame_err=%0d held=%0d ignored_start=%0d midreset=%0d loop=%0d duplex=%0d",
                     c_tx, c_rx, c_tol, c_ferr, c_held, c_ignored, c_midreset, c_loop, c_duplex);
            $display("CHECKS total=%0d mismatches=%0d", checks, errors);
            if (errors == 0)
                $display("[TB] PASS");
            else
                $display("[TB] FAIL: %0d mismatches, first at %0t", errors, first_err_time);
        end
    endtask

    initial begin                               // 시간 초과 감시 (DUT가 멈춰도 로그를 남긴다)
        #15_000_000;                            // 15ms: 골든 종료 시각의 약 3배. 멈춘 DUT에서 xsim 실행 시간이 길어지지 않게 한다
        check("tb_timeout", 0, 1);
        report;
        $finish;
    end

    initial begin
        ck = 0; reset = 0; tx_start = 0; tx_data = 8'h00; rx_drv = 1; loop = 0;
        errors = 0; checks = 0; first_err_time = 0; n_valid = 0; mon_tick = 0; r_last = 8'h00;
        c_tx = 0; c_rx = 0; c_tol = 0; c_ferr = 0; c_held = 0; c_ignored = 0; c_midreset = 0; c_loop = 0; c_duplex = 0;
        seed = 32'h2468_ACE1;
        $timeformat(-9, 0, " ns", 0);

        // 1) 리셋 후 유휴 2비트: tx=1, tx_busy=0, data_valid=0
        #3;
        do_reset;
        mon_tick = 1;
        wait_cyc(BIT*2);
        check("tx_idle_high", 1, tx);
        check("tx_idle_busy", 0, tx_busy);
        check("data_valid_idle", 0, data_valid);

        // 2) TX: 비대칭 데이터 (LSB first 확인), tx_start를 넣는 시점을 tick 위상 곳곳으로
        tx_frame(8'hB1, 0, 1); tx_end(t_e);
        tx_frame(8'h80, 0, 1); tx_end(t_e);
        tx_frame(8'h01, 0, 1); tx_end(t_e);
        tx_frame(8'h3C, 0, 1); tx_end(t_e);
        for (k = 0; k < 6; k = k + 1) begin
            repeat (BIT*k/6 + 7) @(negedge ck);
            rd = {$random(seed)} % 256;
            tx_frame(rd, 0, 1); tx_end(t_e);
        end

        // 3) TX: tx_start 유지 -> 3프레임 연속 (stop 뒤 1비트 유휴 후 다음 start, tx_busy는 계속 1)
        tx_frame(8'hA6, 1, 1);
        e0 = t_e;
        tx_check_bits(e0 + BIT*11, 8'hA6);
        tx_check_bits(e0 + BIT*22, 8'hA6);
        @(negedge ck);
        tx_start = 0;
        tx_end(e0 + BIT*22);
        c_held = c_held + 1;

        // 4) TX: 전송 중 tx_start는 무시된다 (추가 프레임 없음)
        tx_frame(8'h5D, 0, 1);
        e0 = t_e;
        wait_cyc(e0 + BIT*4 + 100);
        @(negedge ck); tx_start = 1; tx_data = 8'hFF;
        repeat (3) @(negedge ck); tx_start = 0;
        tx_end(e0);
        c_ignored = c_ignored + 1;

        // 5) RX: 비대칭 데이터, 정확한 비트 주기
        rx_frame(8'hB1, BIT, 1);
        rx_frame(8'h80, BIT, 1);
        rx_frame(8'h01, BIT, 1);
        rx_frame(8'hF0, BIT, 1);
        rx_frame(8'h00, BIT, 1);
        rx_frame(8'hFF, BIT, 1);

        // 6) RX: TB 비트 주기 ±2% (mid-bit 샘플링이면 여유가 있다)
        for (k = 0; k < 3; k = k + 1) begin
            rx_frame({$random(seed)} % 256, BIT - 9, 1); c_tol = c_tol + 1;
            rx_frame({$random(seed)} % 256, BIT + 9, 1); c_tol = c_tol + 1;
        end

        // 7) RX: stop 비트가 0이면 data_valid 없이 rx_data 유지, 다음 프레임은 정상
        rx_frame(8'h6E, BIT, 0);
        rx_frame(8'h29, BIT, 1);
        rx_frame(8'hC3, BIT, 0);
        rx_frame(8'h94, BIT, 1);

        // 8) TX와 RX 동시 동작 (서로 독립)
        fork
            begin tx_frame(8'hE7, 0, 1); tx_end(t_e); end
            begin repeat (300) @(negedge ck); rx_frame(8'h18, BIT, 1); end
        join
        c_duplex = c_duplex + 1;

        // 9) TX 전송 중 리셋: tx=1, tx_busy=0으로 돌아가고 남은 프레임은 나오지 않는다. 이후 정상
        tx_frame(8'h96, 0, 0);                    // 비트 검사는 아래 fork에서 리셋 전까지만
        e0 = t_e;
        fork : midtx
            tx_check_bits(e0, 8'h96);
            begin wait_cyc(e0 + BIT*5 + 123); disable midtx; end
        join
        mon_tick = 0;
        do_reset;
        r_last = 8'h00;
        mon_tick = 1;
        wait_cyc(BIT*3);
        check("tx_idle_high", 1, tx);
        check("tx_idle_busy", 0, tx_busy);
        tx_frame(8'h4B, 0, 1); tx_end(t_e);
        c_midreset = c_midreset + 1;

        // 10) RX 수신 중 리셋: data_valid 없음, rx_data=0, 이후 정상
        rx_frame(8'hD2, BIT, 1);
        r_nv = n_valid;
        fork : midrx
            begin @(negedge ck); rx_drv = 0; repeat (BIT*4) @(negedge ck); rx_drv = 1; repeat (BIT) @(negedge ck); rx_drv = 0; end
            begin repeat (BIT*5 + 200) @(negedge ck); disable midrx; end
        join
        mon_tick = 0;
        do_reset;
        r_last = 8'h00;
        mon_tick = 1;
        wait_cyc(BIT*11);
        check("data_valid_count", r_nv, n_valid);
        check("rx_data_hold", 8'h00, rx_data);
        rx_frame(8'h7A, BIT, 1);
        c_midreset = c_midreset + 1;

        // 11) 루프백 (tx -> rx): 보낸 바이트가 그대로 수신된다
        loop = 1;
        for (k = 0; k < 4; k = k + 1) begin
            rd = (k == 0) ? 8'hC5 : {$random(seed)} % 256;
            r_nv = n_valid;
            tx_frame(rd, 0, 1);
            wait_cyc(t_e + VALID + 2);
            check("loop_data_valid_count", r_nv + 1, n_valid);
            check("loop_rx_data", rd, rx_data);
            tx_end(t_e);
            c_loop = c_loop + 1;
        end
        loop = 0;

        // 12) 끝: 유휴 상태 확인
        wait_cyc(cyc + BIT*2);
        check("tx_idle_high", 1, tx);
        check("tx_idle_busy", 0, tx_busy);
        check("data_valid_idle", 0, data_valid);
        report;
        $finish;
    end
endmodule
