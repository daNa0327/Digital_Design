module UART_RX (
    input ck,
    input reset,
    input rx,

    output reg data_valid,
    output reg [7:0] rx_data
);
    reg [7:0] data_tmp;
    reg [2:0] bit_idx;

    // 기존 UART RX 모듈에서 Mid-bit Sampling 기능 추가
    reg [8:0] baud_count; // 2^9 = 512 > 433
    parameter CLK_FREQ = 50_000_000;
    parameter BAUD_RATE = 115200;
    localparam BAUD_CNT = CLK_FREQ / BAUD_RATE - 1;

    reg [1:0] state;
    localparam IDLE  = 2'b00;
    localparam START = 2'b01;
    localparam DATA  = 2'b10;
    localparam STOP  = 2'b11;

    always @(posedge ck or posedge reset) begin
        
        if(reset) begin
            state <= IDLE;
            baud_count <= 0;
            bit_idx <= 0;
            rx_data <= 0;
            data_tmp <= 0;
            data_valid <= 0;
        end
        else begin
            case(state)
                IDLE: begin
                    data_valid <= 0;
                    if(rx == 0) begin
                        baud_count <= 0;
                        state <= START;
                    end
                end
                START: begin
                    if (baud_count == BAUD_CNT/2) begin // 0.5비트를 대기 후 상태 전환
                        baud_count <= 0;
                        bit_idx <= 0;
                        state <= DATA;
                    end
                    else begin
                        baud_count <= baud_count + 1;
                    end
                end
                DATA: begin
                    if (baud_count == BAUD_CNT) begin
                        baud_count <= 0;
                        data_tmp[bit_idx] <= rx;
                        if (bit_idx == 7)
                            state <= STOP;
                        else
                            bit_idx <= bit_idx + 1;
                    end
                    else begin
                        baud_count <= baud_count + 1;
                    end
                end
                STOP: begin
                    if (baud_count == BAUD_CNT) begin
                        baud_count <= 0;

                        if (rx == 1) begin
                            rx_data <= data_tmp;
                            data_valid <= 1;
                        end

                        state <= IDLE;
                    end
                    else begin
                        baud_count <= baud_count + 1;
                    end
                end
            endcase
        end
    end
endmodule
