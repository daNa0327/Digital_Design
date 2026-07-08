module Half_Subtractor (B, D, X, Y);

    input X, Y;
    output B, D;

    assign B = ~X & Y;
    assign D =  X ^ Y;
endmodule

module Top;

    reg X, Y;
    wire B, D;

    Half_Subtractor m1(B, D, X, Y);

    initial begin
        #1 X = 0; Y = 0;
        $monitor("X = %d Y = %d / B = %d D = %d", X, Y, B, D);
        #1 X = 0; Y = 1;
        #1 X = 1; Y = 0;
        #1 X = 1; Y = 1;
    end
endmodule
