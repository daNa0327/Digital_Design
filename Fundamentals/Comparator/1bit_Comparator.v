module bit1_Comparator(G, L, E, A, B);

    input A, B;
    output G, L, E; // Greater, Less, Equal

    assign G =  A & ~B;
    assign L = ~A &  B;
    assign E = ~(A ^ B);
endmodule

module Top;

    wire G, L, E;
    reg A, B;

    bit1_Comparator m1(G, L, E, A, B);

    initial begin
        $monitor("A = %d B = %d / G = %d L = %d E = %d", A, B, G, L, E);

        #1 A = 0; B = 0; // A = B
        #1 A = 0; B = 1; // A < B
        #1 A = 1; B = 0; // A > B
        #1 A = 1; B = 1; // A = B

        #10 $finish;
    end
endmodule
