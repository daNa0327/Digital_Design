module Traffic_Light (
    input ck,
    input reset,

    output reg HG, HY, HR,
    output reg VG, VY, VR
);
    wire [1:0] state;

    Traffic_fsm t1(
        .ck(ck),
        .reset(reset),
        .state(state)
    );

    always @(*) begin
        case(state)
            2'b00: begin // HG VR
                HG = 1; HY = 0; HR = 0;
                VG = 0; VY = 0; VR = 1;
            end
            2'b01: begin // HY VR
                HG = 0; HY = 1; HR = 0; 
                VG = 0; VY = 0; VR = 1;
            end
            2'b10: begin // HR VG
                HG = 0; HY = 0; HR = 1; 
                VG = 1; VY = 0; VR = 0;
            end
            2'b11: begin // HR VY
                HG = 0; HY = 0; HR = 1; 
                VG = 0; VY = 1; VR = 0;
            end
            default: begin
                HG = 0; HY = 0; HR = 0;
                VG = 0; VY = 0; VR = 0;
             end
        endcase
    end
endmodule
