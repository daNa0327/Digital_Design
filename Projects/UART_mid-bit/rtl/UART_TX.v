module UART_TX (
    input ck,
    input reset,
    input baud_tick,
    input tx_start,
    input [7:0] tx_data,

    output reg tx,
    output reg busy
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
            tx    <= 1;
            busy  <= 0;
            state <= IDLE;
        end
        else if (baud_tick) begin
            case(state)
                IDLE: begin
                    if (tx_start == 1) begin
                        state    <= START;
                        bit_idx  <= 0;
                        data_tmp <= tx_data;
                    end 
                    else begin
                        tx   <= 1;
                        busy <= 0;
                    end
                end
                START: begin
                    tx    <= 0;
                    busy  <= 1;
                    state <= DATA;
                end
                DATA: begin
                    tx   <= data_tmp[bit_idx];
                    busy <= 1;
                    if (bit_idx == 7) begin
                        state <= STOP;
                    end
                    else begin
                        bit_idx <= bit_idx + 1;
                    end
                end
                STOP: begin
                    tx    <= 1;
                    busy  <= 1;
                    state <= IDLE;
                end
            endcase
        end
    end
endmodule
