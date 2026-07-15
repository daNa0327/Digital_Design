module UART_RX (
    input ck,
    input reset,
    input baud_tick,
    input rx,

    output reg data_valid,
    output reg [7:0] rx_data
);
    reg [7:0] data_tmp;
    reg [2:0] bit_idx;

    reg [1:0] state;
    localparam IDLE  = 2'b00;
    localparam START = 2'b01;
    localparam DATA  = 2'b10;
    localparam STOP  = 2'b11;

    always @(posedge ck or posedge reset) begin
        if(reset) begin
            state      <= IDLE;
            data_valid <= 0;
        end
        else if (baud_tick) begin
            case(state)
                IDLE: begin
                    data_valid <= 0;
                    if(rx == 0) begin
                        state <= START;
                    end
                end
                START: begin
                    bit_idx <= 1;       // 비트 밀림 현상 때문에 임의로 index 1부터 시작
                    data_tmp[0] <= rx;  // 및 index 0 값은 START 상태에서 입력
                    state <= DATA;
                end
                DATA: begin
                    data_tmp[bit_idx] <= rx;
                    if (bit_idx == 7) begin
                        state <= STOP;
                    end
                    else begin
                        bit_idx <= bit_idx + 1;
                    end
                end
                STOP: begin
                    if (rx == 1) begin
                        rx_data    <= data_tmp;
                        data_valid <= 1;
                    end
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule
