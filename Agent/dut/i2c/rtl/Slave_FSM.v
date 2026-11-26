/*
IDLE
 ↓
START 검출
 ↓
ADDR 검출 (주소가 다르면 IDLE로 돌아가 STOP까지 무시)
 ↓
ACK_A
 ↓
WRITE / READ
 ↓
ACK_W (Slave ACK) / ACK_R (Master의 ACK/NACK)
 ↓
IDLE
*/
module Slave_FSM (
    input ck,
    input reset,
    input SCL,
    input sda_in,
    input [7:0] rx_shreg,   // Slave_RX가 모은 비트 (주소 비교용)
    input tx_bit,           // Slave_TX가 내보낼 현재 비트

    output reg sda_low,
    output reg rx_shift,
    output reg rx_latch,
    output reg tx_load,
    output reg tx_shift
);
    parameter SLAVE_ADDR = 7'h42;

    reg [2:0] state;
    localparam IDLE  = 3'd0;
    localparam ADDR  = 3'd1;
    localparam ACK_A = 3'd2;
    localparam WRITE = 3'd3;
    localparam ACK_W = 3'd4;
    localparam READ  = 3'd5;
    localparam ACK_R = 3'd6;

    // SCL, SDA를 ck로 한 번 저장해 에지와 START/STOP 조건을 검출
    reg scl_q;
    reg sda_q;
    wire scl_rise  = SCL & ~scl_q;
    wire scl_fall  = ~SCL & scl_q;
    wire start_det = SCL & scl_q & sda_q & ~sda_in;   // SCL high에서 SDA 하강
    wire stop_det  = SCL & scl_q & ~sda_q & sda_in;   // SCL high에서 SDA 상승

    reg [3:0] bit_cnt; // 0 ~ 8
    reg rw_q;

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            scl_q    <= 1'b1;
            sda_q    <= 1'b1;
            sda_low  <= 1'b0;
            rx_shift <= 1'b0;
            rx_latch <= 1'b0;
            tx_load  <= 1'b0;
            tx_shift <= 1'b0;
            bit_cnt  <= 4'd0;
            rw_q     <= 1'b0;
            state    <= IDLE;
        end
        else begin
            scl_q    <= SCL;
            sda_q    <= sda_in;
            rx_shift <= 1'b0;
            rx_latch <= 1'b0;
            tx_load  <= 1'b0;
            tx_shift <= 1'b0;

            if (start_det) begin
                sda_low <= 1'b0;
                bit_cnt <= 4'd0;
                state   <= ADDR;
            end
            else if (stop_det) begin
                sda_low <= 1'b0;
                state   <= IDLE;
            end
            else begin
                case(state)
                    IDLE: begin
                        sda_low <= 1'b0;
                    end

                    ADDR: begin
                        if (scl_rise) begin
                            rx_shift <= 1'b1;
                            bit_cnt  <= bit_cnt + 1'b1;
                        end
                        if (scl_fall && bit_cnt == 4'd8) begin   // 주소 7비트 + R/W 수신 완료
                            bit_cnt <= 4'd0;
                            if (rx_shreg[7:1] == SLAVE_ADDR) begin
                                sda_low <= 1'b1;                 // ACK
                                rw_q    <= rx_shreg[0];
                                tx_load <= 1'b1;                 // 읽기라면 다음 비트부터 보낼 데이터를 미리 적재
                                state   <= ACK_A;
                            end
                            else begin
                                state <= IDLE;                   // 내 주소가 아니면 STOP까지 무시
                            end
                        end
                    end

                    ACK_A: begin
                        if (scl_fall) begin
                            if (rw_q) begin
                                sda_low <= ~tx_bit;              // 읽기: 첫 비트(MSB)를 바로 구동
                                state   <= READ;
                            end
                            else begin
                                sda_low <= 1'b0;
                                state   <= WRITE;
                            end
                        end
                    end

                    WRITE: begin
                        if (scl_rise) begin
                            rx_shift <= 1'b1;
                            bit_cnt  <= bit_cnt + 1'b1;
                        end
                        if (scl_fall && bit_cnt == 4'd8) begin
                            bit_cnt  <= 4'd0;
                            sda_low  <= 1'b1;                    // ACK
                            rx_latch <= 1'b1;
                            state    <= ACK_W;
                        end
                    end

                    ACK_W: begin
                        if (scl_fall) begin
                            sda_low <= 1'b0;
                            state   <= IDLE;
                        end
                    end

                    READ: begin
                        if (scl_rise) begin                      // Master가 샘플한 뒤 다음 비트로 이동
                            tx_shift <= 1'b1;
                            bit_cnt  <= bit_cnt + 1'b1;
                        end
                        if (scl_fall) begin
                            if (bit_cnt == 4'd8) begin
                                bit_cnt <= 4'd0;
                                sda_low <= 1'b0;                 // SDA를 놓고 Master의 ACK/NACK 클록
                                state   <= ACK_R;
                            end
                            else begin
                                sda_low <= ~tx_bit;
                            end
                        end
                    end

                    ACK_R: begin
                        if (scl_fall) state <= IDLE;             // 1바이트 읽기 종료
                    end

                    default: state <= IDLE;
                endcase
            end
        end
    end
endmodule
