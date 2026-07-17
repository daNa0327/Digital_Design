module bit4_Adder(
    input [3:0] A,
    input [3:0] B,
    input Ci,

    output C,
    output [3:0] S
);  
    wire c1;
    FA f1(
        .A(A[0]),
        .B(B[0]),
        .Ci(Ci),

        .C(c1),
        .S(S[0])
    );

    wire c2;
    FA f2(
        .A(A[1]),
        .B(B[1]),
        .Ci(c1),

        .C(c2),
        .S(S[1])
    );

    wire c3;
    FA f3(
        .A(A[2]),
        .B(B[2]),
        .Ci(c2),

        .C(c3),
        .S(S[2])
    );

    FA f4(
        .A(A[3]),
        .B(B[3]),
        .Ci(c3),

        .C(C),
        .S(S[3])
    );

endmodule
