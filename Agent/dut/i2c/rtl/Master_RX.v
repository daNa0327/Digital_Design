/*
SDA -> rx_data[7:0] (MSB first)
*/
module Master_RX (
    input ck,
    input reset,
    input shift,
    input sda_in,

    output reg [7:0] rx_data
);
    always @(posedge ck or posedge reset) begin
        if (reset) begin
            rx_data <= 8'b0;
        end
        else if (shift) begin
            rx_data <= {rx_data[6:0], sda_in};
        end
    end
endmodule
