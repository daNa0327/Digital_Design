module Half_Adder (C, S, A, B);

    input A, B;
    output C, S;

    assign C = A & B;
    assign S = A ^ B;
endmodule

module Top;

    wire C, S;
    reg A, B;

    Half_Adder m1(C, S, A, B);

    initial begin
        #1 A = 0; B = 0;
        $monitor("A = %d B = %d / C = %d S = %d", A, B, C, S);
        #1 A = 0; B = 1;
        #1 A = 1; B = 0;
        #1 A = 1; B = 1;
    end
endmodule
