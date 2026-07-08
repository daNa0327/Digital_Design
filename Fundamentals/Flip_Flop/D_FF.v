module D_FF (
    output reg Q,
    input D,
    input CK
);

always @(posedge CK) begin
    Q <= D;     // D = 0: Reset, 1: Set
end

endmodule

module Top;
    reg D, CK;
    wire Q;

    always #1 CK = ~CK;

    D_FF m1(Q, D, CK);

    initial begin
        CK = 0;
        D = 0;

        $monitor("CK = %b / D = %b / Q = %b", CK, D, Q);

        #3 D = 1;   // Set
        #3 D = 0;   // Reset
        #3 D = 1;   // Set
        #3 D = 0;   // Reset
        
        #1 $finish;
    end
endmodule
