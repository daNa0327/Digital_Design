// NOTE: 일부러 `timescale 지시문을 쓰지 않는다 (골든 RTL에 없고, xsim은 섞이면 XSIM 43-4099 에러).
//       지시문이 없으면 xsim 기본값(1ns/1ps)이 적용되어 #10은 10ns, ck 주기는 20ns가 된다.
// Self-checking testbench for i2c_system (I2C Master + Slave 폐루프, 7비트 주소, 1바이트 쓰기/읽기, 100kHz).
// 검증 방식: 블랙박스. 버스(SCL, SDA)와 포트(busy, done, ack_error, *_rx_data)만 명세(dut/i2c/spec.md)와 비교한다.
//   버스 모니터: START/STOP 횟수, SCL 상승 에지마다 SDA 비트 수집(주소+R/W, ACK, 데이터, ACK/NACK),
//               SCL high/low 구간 길이, START 뒤 SCL 하강까지, SCL 상승 뒤 STOP까지의 시간
//   트랜잭션 단위: 비트열, ack_error, rx_data 갱신/유지, done 폭, 끝난 뒤 버스 유휴
// 자극: 쓰기/읽기 비대칭 데이터, 주소 불일치(NACK), 고정 seed 랜덤, start 유지(연속), 트랜잭션 중 리셋.
// 로그 규약(Agent가 파싱): 불일치는 "CHECK_FAIL ..." 줄로 최대 10개, 마지막에 "[TB] PASS" 또는 "[TB] FAIL: ..." 한 줄.
module i2c_sc_tb;
    reg        ck;
    reg        reset;
    reg        start;
    reg        rw;
    reg  [6:0] addr;
    reg  [7:0] mtx;
    reg  [7:0] stx;
    wire [7:0] mrx;
    wire [7:0] srx;
    wire       SCL, SDA, busy, done, ack_error;

    i2c_system dut (
        .ck(ck), .reset(reset), .start(start), .rw(rw), .addr(addr),
        .master_tx_data(mtx), .slave_tx_data(stx),
        .master_rx_data(mrx), .slave_rx_data(srx),
        .SCL(SCL), .SDA(SDA), .busy(busy), .done(done), .ack_error(ack_error)
    );

    always #10 ck = ~ck;                        // 50MHz. 입력은 negedge에서 바꾼다

    localparam QTR   = 125;                     // SCL 1/4 주기 (ck)
    localparam HALF  = 250;                     // SCL high/low 구간 (ck), SCL 주기 500 ck = 10us
    localparam SLAVE = 7'h42;

    // ------------------------------------------------------------
    // 판정 도우미 (check 태스크가 참조하는 변수는 먼저 선언: xsim은 선언 순서를 엄격히 본다)
    // ------------------------------------------------------------
    integer errors, checks;
    integer cyc;                                // 리셋 해제 후 ck 상승 에지 수 (리셋 중 0)
    integer nbits;                              // 이번 트랜잭션에서 수집한 비트 수
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
                    $display("CHECK_FAIL t=%0t sig=%0s exp=%0h got=%0h (bit=%0d SCL=%b SDA=%b busy=%b done=%b ack_error=%b)",
                             $time, what, exp, got, nbits, SCL, SDA, busy, done, ack_error);
            end
        end
    endtask

    always @(posedge ck or posedge reset)
        if (reset) cyc <= 0;
        else       cyc <= cyc + 1;

    // ------------------------------------------------------------
    // 버스 모니터 (mon=1이고 리셋이 아닐 때만)
    // ------------------------------------------------------------
    reg         mon;
    reg  [18:0] bits;                           // 먼저 받은 비트가 상위. 마지막은 STOP 직전 SCL 상승의 SDA(0)
    integer     n_start, n_stop;
    integer     t_rise, t_fall, t_start;

    always @(posedge SCL) begin
        #1;
        if (mon && !reset) begin
            if (nbits == 0) check("scl_first_low", HALF + QTR, cyc - t_fall);
            else            check("scl_low", HALF, cyc - t_fall);
            bits  = {bits[17:0], SDA};          // SDA는 SCL high 동안 안정해야 한다
            nbits = nbits + 1;
            t_rise = cyc;
        end
    end

    always @(negedge SCL) begin
        #1;
        if (mon && !reset) begin
            if (nbits == 0) check("start_hold", 2*QTR, cyc - t_start);
            else            check("scl_high", HALF, cyc - t_rise);
            t_fall = cyc;
        end
    end

    always @(SDA) begin
        #1;
        if (mon && !reset && SCL) begin         // SCL high에서 SDA 변화는 START(하강) 또는 STOP(상승)뿐
            if (!SDA) begin
                n_start = n_start + 1;
                t_start = cyc;
            end else begin
                n_stop = n_stop + 1;
                check("stop_setup", QTR, cyc - t_rise);
            end
        end
    end

    // 커버리지 카운터
    integer c_wr, c_rd, c_nack, c_held, c_midreset;

    // ------------------------------------------------------------
    // 자극 / 검사 태스크
    // ------------------------------------------------------------
    task do_reset;                              // 비동기 리셋 5 ck. 리셋 중 상태를 확인한다
        begin
            mon = 0;
            @(negedge ck);
            reset = 1; start = 0;
            #1;
            check("SCL_reset", 1, SCL);
            check("SDA_reset", 1, SDA);
            check("busy_reset", 0, busy);
            check("done_reset", 0, done);
            check("ack_error_reset", 0, ack_error);
            check("master_rx_reset", 0, mrx);
            check("slave_rx_reset", 0, srx);
            repeat (5) @(negedge ck);
            reset = 0;
            mon = 1;
        end
    endtask

    task wait_sig;                              // sig가 val이 될 때까지 (최대 n ck). 시간 초과면 실패 기록
        input [8*24-1:0] what;
        input integer    which;                 // 0: busy, 1: done
        input            val;
        input integer    n;
        integer g;
        begin
            g = 0;
            while (((which == 0) ? busy : done) !== val && g < n) begin @(posedge ck); #1; g = g + 1; end
            if (g >= n) check(what, val, ~val);
        end
    endtask

    reg  [7:0] last_mrx, last_srx;
    reg        x_match;
    integer    x_nb, x_t;
    task begin_xact;                            // 입력을 정하고 start를 busy가 오를 때까지 유지한다
        input       r;
        input [6:0] a;
        input [7:0] m;
        input [7:0] s;
        input       hold;                       // 1이면 start를 내리지 않는다
        begin
            @(negedge ck);
            rw = r; addr = a; mtx = m; stx = s;
            n_start = 0; n_stop = 0; nbits = 0; bits = 0;
            start = 1;
            wait_sig("busy_rise_timeout", 0, 1, 4*QTR);
            if (!hold) begin @(negedge ck); start = 0; end
        end
    endtask

    task end_xact;                              // done 상승까지 기다려 비트열과 결과를 확인한다
        input       r;
        input [6:0] a;
        input [7:0] m;
        input [7:0] s;
        begin
            x_match = (a == SLAVE);
            x_nb    = x_match ? 19 : 10;                // 데이터/ACK 비트 + STOP 직전의 SCL 상승 1번
            wait_sig("done_rise_timeout", 1, 1, 30*4*QTR);
            check("busy_at_done", 0, busy);
            check("start_count", 1, n_start);
            check("stop_count", 1, n_stop);
            check("bit_count", x_nb, nbits);
            check("addr_bits", {a, r}, x_match ? bits[18:11] : bits[9:2]);
            check("addr_ack", x_match ? 0 : 1, x_match ? bits[10] : bits[1]);
            check("stop_sda_low", 0, bits[0]);
            check("ack_error", x_match ? 0 : 1, ack_error);
            if (x_match) begin
                check("data_bits", r ? s : m, bits[9:2]);
                check("data_ack", r ? 1 : 0, bits[1]);   // 쓰기: Slave ACK(0), 읽기: Master NACK(1)
                if (r) last_mrx = s; else last_srx = m;
                if (r) c_rd = c_rd + 1; else c_wr = c_wr + 1;
            end else
                c_nack = c_nack + 1;
            check("master_rx_data", last_mrx, mrx);
            check("slave_rx_data", last_srx, srx);
            x_t = cyc;                          // done 폭: 4 tick (SCL 1주기)
            wait_sig("done_fall_timeout", 1, 0, 8*QTR);
            check("done_width", 4*QTR, cyc - x_t);
        end
    endtask

    task bus_idle;                              // 유휴: SCL=1, SDA=1, busy=0, done=0, rx 유지
        input integer n;
        integer g;
        begin
            for (g = 0; g < n; g = g + QTR) begin
                repeat (QTR) @(posedge ck);
                #1;
                check("SCL_idle", 1, SCL);
                check("SDA_idle", 1, SDA);
                check("busy_idle", 0, busy);
                check("done_idle", 0, done);
                check("master_rx_hold", last_mrx, mrx);
                check("slave_rx_hold", last_srx, srx);
            end
        end
    endtask

    task xact;
        input       r;
        input [6:0] a;
        input [7:0] m;
        input [7:0] s;
        begin
            begin_xact(r, a, m, s, 0);
            end_xact(r, a, m, s);
            bus_idle(2*HALF);
        end
    endtask

    integer k, seed;
    reg [7:0] rm, rs;
    reg       rr;

    task report;
        begin
            $display("COVER write=%0d read=%0d nack=%0d held=%0d midreset=%0d", c_wr, c_rd, c_nack, c_held, c_midreset);
            $display("CHECKS total=%0d mismatches=%0d", checks, errors);
            if (errors == 0)
                $display("[TB] PASS");
            else
                $display("[TB] FAIL: %0d mismatches, first at %0t", errors, first_err_time);
        end
    endtask

    initial begin                               // 시간 초과 감시 (DUT가 멈춰도 로그를 남긴다)
        #20_000_000;                            // 20ms: 골든 종료 시각의 약 3배. 멈춘 DUT에서 xsim 실행 시간이 길어지지 않게 한다
        check("tb_timeout", 0, 1);
        report;
        $finish;
    end

    initial begin
        ck = 0; reset = 0; start = 0; rw = 0; addr = 7'h00; mtx = 8'h00; stx = 8'h00;
        errors = 0; checks = 0; first_err_time = 0; mon = 0;
        nbits = 0; bits = 0; n_start = 0; n_stop = 0; t_rise = 0; t_fall = 0; t_start = 0;
        last_mrx = 8'h00; last_srx = 8'h00;
        c_wr = 0; c_rd = 0; c_nack = 0; c_held = 0; c_midreset = 0;
        seed = 32'h0BAD_C0DE;
        $timeformat(-9, 0, " ns", 0);

        // 1) 리셋 + 유휴
        #3;
        do_reset;
        bus_idle(4*HALF);

        // 2) 쓰기: 비대칭 데이터 (MSB first, 방향 확인)
        xact(0, SLAVE, 8'hB1, 8'h00);
        xact(0, SLAVE, 8'h80, 8'h00);
        xact(0, SLAVE, 8'h01, 8'h00);

        // 3) 읽기: 비대칭 데이터
        xact(1, SLAVE, 8'h00, 8'h6C);
        xact(1, SLAVE, 8'h00, 8'h80);
        xact(1, SLAVE, 8'h00, 8'h01);

        // 4) 주소 불일치: NACK, ack_error=1, 데이터 단계 없이 STOP, rx 유지. 다음 정상 트랜잭션에서 ack_error=0
        xact(0, 7'h43, 8'h5A, 8'h00);           // 최하위 비트만 다름
        xact(1, 7'h02, 8'h00, 8'hA5);           // 최상위 비트만 다름
        xact(0, SLAVE, 8'hE7, 8'h00);
        xact(1, 7'h21, 8'h00, 8'h3C);           // 한 칸 밀린 주소
        xact(1, SLAVE, 8'h00, 8'hC3);

        // 5) 고정 seed 랜덤 (쓰기/읽기 섞음)
        for (k = 0; k < 8; k = k + 1) begin
            rr = {$random(seed)} % 2;
            rm = {$random(seed)} % 256;
            rs = {$random(seed)} % 256;
            xact(rr, SLAVE, rm, rs);
        end

        // 6) start 유지: 트랜잭션 2회 연속 (같은 입력)
        begin_xact(0, SLAVE, 8'h96, 8'h00, 1);
        end_xact(0, SLAVE, 8'h96, 8'h00);
        n_start = 0; n_stop = 0; nbits = 0; bits = 0;
        wait_sig("busy_rise_timeout", 0, 1, 8*QTR);
        @(negedge ck); start = 0;
        end_xact(0, SLAVE, 8'h96, 8'h00);
        bus_idle(2*HALF);
        c_held = c_held + 1;

        // 7) 트랜잭션 중 리셋 (주소 단계, 쓰기 데이터 단계, 읽기 데이터 단계) 뒤 정상 동작
        begin_xact(0, SLAVE, 8'h4B, 8'h00, 0);
        repeat (6*4*QTR) @(negedge ck);
        do_reset;
        last_mrx = 8'h00; last_srx = 8'h00;
        bus_idle(2*HALF);
        xact(0, SLAVE, 8'hD2, 8'h00);
        c_midreset = c_midreset + 1;

        begin_xact(0, SLAVE, 8'h2D, 8'h00, 0);
        repeat (14*4*QTR) @(negedge ck);
        do_reset;
        last_mrx = 8'h00; last_srx = 8'h00;
        bus_idle(2*HALF);
        xact(1, SLAVE, 8'h00, 8'h7E);
        c_midreset = c_midreset + 1;

        begin_xact(1, SLAVE, 8'h00, 8'hF0, 0);
        repeat (15*4*QTR + 37) @(negedge ck);
        do_reset;
        last_mrx = 8'h00; last_srx = 8'h00;
        bus_idle(2*HALF);
        xact(1, SLAVE, 8'h00, 8'h0F);
        xact(0, SLAVE, 8'h69, 8'h00);
        c_midreset = c_midreset + 1;

        // 8) 끝: 유휴 확인
        bus_idle(4*HALF);
        report;
        $finish;
    end
endmodule
