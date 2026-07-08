module SR_FF (
    output reg Q,
    input J, K,
    input CK
);

always @(posedge CK) begin
    case ({J, K})
        2'b00: Q <= Q;      // Hold
        2'b01: Q <= 0;      // Reset
        2'b10: Q <= 1;      // Set
        2'b11: Q <= ~Q;     // Toggle

        default: Q <= Q; 
    endcase
end

endmodule

module Top;

    reg J, K, CK;
    wire Q;

    always #1 CK = ~CK;

    SR_FF m1(Q, J, K, CK);

    initial begin
        CK = 0;
        J = 0; K = 0;

        $monitor("CK = %b / J = %b K = %b / Q=%b", CK, J, K, Q);

        #3 J = 1; K = 0;   // Set
        #3 J = 0; K = 0;   // Hold
        #3 J = 0; K = 1;   // Reset
        #3 J = 0; K = 0;   // Hold
        #3 J = 1; K = 1;   // Toggle
        #3 J = 0; K = 0;   // Hold
        
        #1 $finish;
    end
endmodule
