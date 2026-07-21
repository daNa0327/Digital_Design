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
    localparam LOAD     = 2'b01;
    localparam TRANSFER = 2'b10;
    localparam DONE     = 2'b11;

    reg [2:0] bit_cnt;

    always @(posedge spi_clk or posedge reset) begin
        if (reset) begin
            CS       <= 1;
            load     <= 0;
            shift_en <= 0;
            busy     <= 0;
            done     <= 0;
            bit_cnt  <= 0;
            state    <= IDLE;
        end
        else begin
            case(state)
                IDLE: begin
                    CS       <= 1;
                    load     <= 0;
                    shift_en <= 0;
                    busy     <= 0;
                    done     <= 0;

                    if(start) begin
                        state <= LOAD;
                    end
                end
                LOAD: begin
                    CS       <= 0;
                    load     <= 1;
                    shift_en <= 0;
                    busy     <= 1;
                    done     <= 0;

                    bit_cnt  <= 0;
                    state    <= TRANSFER;
                end
                TRANSFER: begin
                    CS       <= 0;
                    load     <= 0;
                    shift_en <= 1;
                    busy     <= 1;
                    done     <= 0;

                    if (bit_cnt == 7) begin
                        state <= DONE;
                    end
                    else begin
                        bit_cnt <= bit_cnt + 1;
                    end
                end
                DONE: begin
                    CS       <= 1;
                    load     <= 0;
                    shift_en <= 0;
                    busy     <= 0;
                    done     <= 1;

                    state    <= IDLE;
                end
            endcase
        end
    end
endmodule
