module Traffic_Light (
    input ck,
    input reset,

    output reg HG, HY, HR,
    output reg VG, VY, VR
);
    wire [1:0] state;

    wire clk_1hz;
    clock_divider c1(
        .ck(ck),
        .reset(reset),
        .clk_1hz(clk_1hz)
    );

    Traffic_fsm t1(
        .ck(clk_1hz),
        .reset(reset),
        .state(state)
    );

    always @(*) begin
        HG = 0; HY = 0; HR = 0;
        VG = 0; VY = 0; VR = 0;
        case(state)
            2'b00: begin // HG VR
                HG = 1; VR = 1;
            end
            2'b01: begin // HY VR
                HY = 1; VR = 1;
            end
            2'b10: begin // HR VG
                HR = 1; VG = 1;
            end
            2'b11: begin // HR VY
                HR = 1; VY = 1;
            end
            default: begin
                HG = 0; HY = 0; HR = 0;
                VG = 0; VY = 0; VR = 0;
             end
        endcase
    end
endmodule
