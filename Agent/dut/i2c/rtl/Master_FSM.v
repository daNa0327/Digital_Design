/*
IDLE
 ↓
START
 ↓
ADDR (주소 7비트 + R/W)
 ↓
ACK_A (Slave의 주소 ACK, NACK이면 STOP)
 ↓
WRITE / READ
 ↓
ACK_W (Slave ACK) / NACK_R (Master NACK: 1바이트 읽기 종료)
 ↓
STOP
 ↓
DONE
*/
module Master_FSM(
    input ck,
    input reset,
    input tick,
    input start,
    input rw,       // 0: write, 1: read
    input tx_bit,   // Master_TX가 내보낼 현재 비트
    input sda_in,   // 버스의 SDA

    output reg SCL,
    output reg sda_low, // 1이면 SDA를 0으로 당김, 0이면 놓음(pull-up으로 1)
    output reg load_addr,
    output reg load_data,
    output reg tx_shift,
    output reg rx_shift,
    output reg busy,
    output reg done,
    output reg ack_error
);
    reg [3:0] state;
    localparam IDLE   = 4'd0;
    localparam START  = 4'd1;
    localparam ADDR   = 4'd2;
    localparam ACK_A  = 4'd3;
    localparam WRITE  = 4'd4;
    localparam ACK_W  = 4'd5;
    localparam READ   = 4'd6;
    localparam NACK_R = 4'd7;
    localparam STOP   = 4'd8;
    localparam DONE   = 4'd9;

    // 한 비트 = tick 4번. phase 0: SDA 변경(SCL low), 1: SCL 상승, 2: SDA 샘플(SCL high), 3: SCL 하강
    reg [1:0] phase;
    reg [2:0] bit_cnt;
    reg rw_q;

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            SCL       <= 1'b1;
            sda_low   <= 1'b0;
            load_addr <= 1'b0;
            load_data <= 1'b0;
            tx_shift  <= 1'b0;
            rx_shift  <= 1'b0;
            busy      <= 1'b0;
            done      <= 1'b0;
            ack_error <= 1'b0;
            phase     <= 2'd0;
            bit_cnt   <= 3'd0;
            rw_q      <= 1'b0;
            state     <= IDLE;
        end
        else begin
            // 제어 펄스는 1 ck만 유지
            load_addr <= 1'b0;
            load_data <= 1'b0;
            tx_shift  <= 1'b0;
            rx_shift  <= 1'b0;

            if (tick) begin
                case(state)
                    IDLE: begin
                        SCL     <= 1'b1;
                        sda_low <= 1'b0;
                        busy    <= 1'b0;
                        done    <= 1'b0;
                        phase   <= 2'd0;
                        bit_cnt <= 3'd0;

                        if (start) begin
                            rw_q      <= rw;
                            load_addr <= 1'b1;
                            busy      <= 1'b1;
                            ack_error <= 1'b0;
                            state     <= START;
                        end
                    end

                    START: begin
                        phase <= phase + 1'b1;
                        if (phase == 2'd0) sda_low <= 1'b1;     // SCL high에서 SDA 하강 = START 조건
                        if (phase == 2'd2) SCL <= 1'b0;
                        if (phase == 2'd3) state <= ADDR;
                    end

                    ADDR, WRITE: begin
                        phase <= phase + 1'b1;
                        case(phase)
                            2'd0: sda_low <= ~tx_bit;           // 0이면 당기고 1이면 놓는다
                            2'd1: SCL <= 1'b1;
                            2'd3: begin
                                SCL      <= 1'b0;
                                tx_shift <= 1'b1;
                                bit_cnt  <= bit_cnt + 1'b1;
                                if (bit_cnt == 3'd7)
                                    state <= (state == ADDR) ? ACK_A : ACK_W;
                            end
                        endcase
                    end

                    ACK_A, ACK_W: begin
                        phase <= phase + 1'b1;
                        case(phase)
                            2'd0: sda_low <= 1'b0;              // SDA를 놓고 Slave의 ACK를 기다림
                            2'd1: SCL <= 1'b1;
                            2'd2: if (sda_in) ack_error <= 1'b1; // SDA가 1이면 NACK
                            2'd3: begin
                                SCL <= 1'b0;
                                if (state == ACK_W || ack_error)
                                    state <= STOP;
                                else if (rw_q)
                                    state <= READ;
                                else begin
                                    load_data <= 1'b1;
                                    state     <= WRITE;
                                end
                            end
                        endcase
                    end

                    READ: begin
                        phase <= phase + 1'b1;
                        case(phase)
                            2'd0: sda_low <= 1'b0;              // Slave가 SDA를 구동
                            2'd1: SCL <= 1'b1;
                            2'd2: rx_shift <= 1'b1;
                            2'd3: begin
                                SCL     <= 1'b0;
                                bit_cnt <= bit_cnt + 1'b1;
                                if (bit_cnt == 3'd7) state <= NACK_R;
                            end
                        endcase
                    end

                    NACK_R: begin
                        phase <= phase + 1'b1;
                        case(phase)
                            2'd0: sda_low <= 1'b0;              // SDA를 놓아 NACK (1바이트 읽기 종료)
                            2'd1: SCL <= 1'b1;
                            2'd3: begin
                                SCL   <= 1'b0;
                                state <= STOP;
                            end
                        endcase
                    end

                    STOP: begin
                        phase <= phase + 1'b1;
                        case(phase)
                            2'd0: sda_low <= 1'b1;              // SCL low에서 SDA를 먼저 내림
                            2'd1: SCL <= 1'b1;
                            2'd2: sda_low <= 1'b0;              // SCL high에서 SDA 상승 = STOP 조건
                            2'd3: begin
                                busy  <= 1'b0;
                                done  <= 1'b1;
                                state <= DONE;
                            end
                        endcase
                    end

                    DONE: begin
                        phase <= phase + 1'b1;
                        if (phase == 2'd3) begin
                            done  <= 1'b0;
                            state <= IDLE;
                        end
                    end

                    default: state <= IDLE;
                endcase
            end
        end
    end
endmodule
