module bit2_Comparator(G, L, E, A0, A1, B0, B1);

    input A0, A1, B0, B1;
    output G, L, E; // Greater, Less, Equal

    assign G = (A0 & ~B0) | (~(A0 ^ B0) & (A1 & ~B1));
    assign L = (~A0 & B0) | (~(A0 ^ B0) & (~A1 & B1));
    assign E = ~(A0 ^ B0) & ~(A1 ^ B1);
endmodule

module Top;

    wire G, L, E;
    reg A0, A1, B0, B1;

    bit2_Comparator m1(G, L, E, A0, A1, B0, B1);

    initial begin
        $monitor("A0 = %d A1 = %d B0 = %d B1 = %d / G = %d L = %d E = %d", A0, A1, B0, B1, G, L, E);

        #1 A0 = 0; A1 =  0; B0 = 0; B1 = 0; // A = B
        #1 A0 = 0; A1 =  0; B0 = 0; B1 = 1; // A < B
        #1 A0 = 0; A1 =  0; B0 = 1; B1 = 0; // A < B
        #1 A0 = 0; A1 =  0; B0 = 1; B1 = 1; // A < B
        #1 A0 = 0; A1 =  1; B0 = 0; B1 = 0; // A < B
        #1 A0 = 0; A1 =  1; B0 = 0; B1 = 1; // A < B
        #1 A0 = 0; A1 =  1; B0 = 1; B1 = 0; // A < B
        #1 A0 = 0; A1 =  1; B0 = 1; B1 = 1; // A < B
        #1 A0 = 1; A1 =  0; B0 = 0; B1 = 0; // A > B
        #1 A0 = 1; A1 =  0; B0 = 0; B1 = 1; // A > B
        #1 A0 = 1; A1 =  0; B0 = 1; B1 = 0; // A = B
        #1 A0 = 1; A1 =  0; B0 = 1; B1 = 1; // A < B
        #1 A0 = 1; A1 =  1; B0 = 0; B1 = 0; // A > B
        #1 A0 = 1; A1 =  1; B0 = 0; B1 = 1; // A > B
        #1 A0 = 1; A1 =  1; B0 = 1; B1 = 0; // A > B
        #1 A0 = 1; A1 =  1; B0 = 1; B1 = 1; // A = B
    end
endmodule
