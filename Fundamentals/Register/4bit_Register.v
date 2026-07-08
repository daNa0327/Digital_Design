module bit4_Register (
    output reg [3:0] Q,
    input [3:0] D,
    input CK
);

    always @(posedge CK) begin
        Q <= D;
        /* Q[3] <= D[3]
           Q[2] <= D[2]
           Q[1] <= D[1]
           Q[0] <= D[0] */
    end
endmodule

module Top;

    reg [3:0] D;
    reg CK;
    wire [3:0] Q;

    bit4_Register m1(Q, D, CK);

    always #1 CK = ~CK;

    initial begin
        CK = 0; D = 4'b0000;

        $monitor("CK = %b / D = %b / Q = %b", CK, D, Q);

        #3 D = 4'b1010;
        #3 D = 4'b1111;
        #3 D = 4'b0101;
        #3 D = 4'b0000;

        #1 $finish;
    end

endmodule
