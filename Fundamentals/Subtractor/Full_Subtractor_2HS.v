module Half_Subtractor (B, D, X, Y);

    input X, Y;
    output B, D;

    assign B = ~X & Y;
    assign D =  X ^ Y;
endmodule

module Top;

    wire BO, BH1, BH2, DH;
    reg X, Y, BI;

    Half_Subtractor m1(BH1, DH, X, Y);
    Half_Subtractor m2(BH2, D, DH, BI);

    assign BO = BH1 | BH2;

    initial begin
        #1 X = 0; Y = 0; BI = 0;
        $monitor("X = %d Y = %d BI = %d / BO = %d D = %d", X, Y, BI, BO, D);
        #1 X = 0; Y = 0; BI = 1;
        #1 X = 0; Y = 1; BI = 0;
        #1 X = 0; Y = 1; BI = 1;
        #1 X = 1; Y = 0; BI = 0;
        #1 X = 1; Y = 0; BI = 1;
        #1 X = 1; Y = 1; BI = 0;
        #1 X = 1; Y = 1; BI = 1;
    end
endmodule
