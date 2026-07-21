module SPI_FSM(
    input spi_clk,
    input reset,
    input start,

    output reg CS,
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

    always @(posedge spi_clk or posedge reset) begin
        if (reset) begin
            CS       <= 1'b1;
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
                    CS       <= 1'b1;
                    load     <= 1'b0;
                    shift_en <= 1'b0;
                    busy     <= 1'b0;
                    done     <= 1'b0;
                    bit_cnt  <= 3'b0;

                    if (start) begin
                        CS       <= 1'b0;
                        load     <= 1'b1;     // TX Data Load
                        shift_en <= 1'b1;     // 즉시 Shift Enable 활성화
                        busy     <= 1'b1;
                        state    <= TRANSFER;
                    end
                end

                TRANSFER: begin
                    CS       <= 1'b0;
                    load     <= 1'b0;         // load는 1클록만 유지
                    shift_en <= 1'b1;
                    busy     <= 1'b1;
                    done     <= 1'b0;

                    if (bit_cnt == 3'd7) begin
                        CS       <= 1'b1;
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
                    CS       <= 1'b1;
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