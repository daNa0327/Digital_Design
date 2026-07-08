module SR_FF (
    output reg Q,
    input S, R,
    input CK
);

always @(posedge CK) begin
    case ({S, R})
        2'b00: Q <= Q;      // Hold
        2'b01: Q <= 0;      // Reset
        2'b10: Q <= 1;      // Set
        2'b11: Q <= 1'bx;   // Invalid

        default: Q <= Q; 
    endcase
end
endmodule

module Top;

    reg S, R, CK;
    wire Q;

    always #1 CK = ~CK;

    SR_FF m1(Q, S, R, CK);

    initial begin
        CK = 0;
        S = 0; R = 0;

        $monitor("CK = %b / S = %b R = %b / Q=%b", CK, S, R, Q);

        #3 S = 1; R = 0;   // Set
        #3 S = 0; R = 0;   // Hold
        #3 S = 0; R = 1;   // Reset
        #3 S = 0; R = 0;   // Hold
        #3 S = 1; R = 1;   // Invalid
        #3 S = 0; R = 0;   // Hold
        
        #1 $finish;
    end
endmodule
