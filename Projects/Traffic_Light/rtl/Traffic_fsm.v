module Traffic_fsm ( 
    input ck,
    input reset,

    output reg [1:0] state
);
    parameter S0 = 2'b00; // HTL = G, VTL = R (10s)
    parameter S1 = 2'b01; // HTL = Y, VTL = R (2s)
    parameter S2 = 2'b10; // HTL = R, VTL = G (10s)
    parameter S3 = 2'b11; // HTL = R, VTL = Y (2s)

    reg [3:0] sec_count; 

    always @(posedge ck or posedge reset) begin
        if(reset) begin // Asynchronous Reset
            state <= S0;
            sec_count <= 0;
        end
        else if ((state == S0 || state == S2) && sec_count == 9) begin
            state <= state + 1;
            sec_count <= 0;
        end
        else if ((state == S1 || state == S3) && sec_count == 1) begin
            state <= state + 1;
            sec_count <= 0;
        end
        else begin
            sec_count <= sec_count + 1;
        end
    end
endmodule
