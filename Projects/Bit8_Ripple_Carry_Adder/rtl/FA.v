module FA (
    input A,
    input B,
    input Ci,

    output C,
    output S
);
    wire Ch;
    wire Sh;
    wire Co;

    HA h1(
        .A(A), 
        .B(B), 
        .C(Ch), 
        .S(Sh)
    );

    HA h2(
        .A(Sh), 
        .B(Ci), 
        .C(Co), 
        .S(S)
    );

    assign C = Ch | Co;

endmodule