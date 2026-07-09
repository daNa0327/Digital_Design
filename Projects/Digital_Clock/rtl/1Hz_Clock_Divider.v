module clock_divider (
    input ck, // ck = 50MHz = 50,000,000Hz
    input reset,
    output reg clk_1hz
);
    reg [25:0] count; // 2^26 = 67,108,864 > 49,999,999

    always @(posedge ck or posedge reset) begin // 1Hz Clock 
        if(reset) begin // Asynchronous Reset
            count <= 0;
            clk_1hz <= 0;
        end
        else if(count == 49) begin // 0.5Hz Toggle
            count <= 0;
            clk_1hz <= ~clk_1hz;
        end
        else begin
            count <= count + 1;
        end
    end
endmodule
