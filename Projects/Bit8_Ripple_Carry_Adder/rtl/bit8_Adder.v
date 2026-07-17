module bit8_Adder (
    input [7:0] A,
    input [7:0] B,

    output C,
    output [7:0] S
);
    wire c1;
    bit4_Adder a1 (
        .A(A[3:0]),
        .B(B[3:0]),
        .Ci(0),

        .C(c1),
        .S(S[3:0])
    );

    bit4_Adder a2 (
        .A(A[7:4]),
        .B(B[7:4]),
        .Ci(c1),

        .C(C),
        .S(S[7:4])
    );
    
endmodule