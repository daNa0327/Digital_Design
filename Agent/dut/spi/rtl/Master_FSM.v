module Master_FSM(
    input spi_clk,
    input reset,
    input start,

    output CS,
    output reg load,
    output reg shift_en,
    output reg busy,
    output reg done
);
    reg [1:0] state;
    localparam IDLE     = 2'b00;
    localparam TRANSFER = 2'b01;
    localparam DONE     = 2'b10;

    reg [2:0] bit_cnt;

    // start를 spi_clk negedge에서 IDLE일 때만 받아 CS와 FSM이 같은 신호(start_q)를 쓴다.
    // start가 spi_clk 위상과 무관하게 들어와도 CS는 항상 negedge 직후에 내려가므로 첫 비트가 밀리지 않는다.
    reg start_q;
    always @(negedge spi_clk or posedge reset) begin
        if (reset) start_q <= 1'b0;
        else       start_q <= start && (state == IDLE);
    end

    // CS 신호: IDLE 상태에서 start가 들어오면 즉시 0, DONE 상태에 도달하면 즉시 1
    assign CS = (state == IDLE && !start_q) ? 1'b1 : ((state == DONE) ? 1'b1 : 1'b0);

    always @(posedge spi_clk or posedge reset) begin
        if (reset) begin
            load     <= 1'b0;
            shift_en <= 1'b0;
            busy     <= 1'b0;
            done     <= 1'b0;
            bit_cnt  <= 3'b0;
            state    <= IDLE;
        end
        else begin
            case(state)
                IDLE: begin
                    load     <= 1'b0;
                    shift_en <= 1'b0;
                    busy     <= 1'b0;
                    done     <= 1'b0;
                    bit_cnt  <= 3'b0;

                    if (start_q) begin
                        load     <= 1'b1;
                        shift_en <= 1'b1;
                        busy     <= 1'b1;
                        state    <= TRANSFER;
                    end
                end

                TRANSFER: begin
                    load     <= 1'b0;
                    shift_en <= 1'b1;
                    busy     <= 1'b1;
                    done     <= 1'b0;

                    // 7번째 클록(bit_cnt==6)을 지나 8번째 클록이 치는 순간 DONE 상태로 전환
                    if (bit_cnt == 3'd6) begin
                        shift_en <= 1'b0;
                        busy     <= 1'b0;
                        done     <= 1'b1;
                        state    <= DONE;
                    end
                    else begin
                        bit_cnt  <= bit_cnt + 1'b1;
                    end
                end

                DONE: begin
                    load     <= 1'b0;
                    shift_en <= 1'b0;
                    busy     <= 1'b0;
                    done     <= 1'b1;

                    state    <= IDLE;
                end

                default: state <= IDLE;
            endcase
        end
    end
endmodule
