module Slave_TX (
    input ck,
    input reset,
    input load,
    input shift,
    input [7:0] tx_data,

    output tx_bit
);
    reg [7:0] tx_reg;

    assign tx_bit = tx_reg[7]; // MSB first

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            tx_reg <= 8'b0;
        end
        else if (load) begin
            tx_reg <= tx_data;
        end
        else if (shift) begin
            tx_reg <= {tx_reg[6:0], 1'b0};
        end
    end
endmodule
