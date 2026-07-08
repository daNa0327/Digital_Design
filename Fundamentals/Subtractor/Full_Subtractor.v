module Full_Subtractor (BO, D, X, Y, BI);

    input X, Y, BI;
    output BO, D;

    assign BO = (~(X ^ Y) & BI) | (~X & Y);
    assign D = X ^ Y ^ BI;
endmodule

module Top;

    reg X, Y, BI;
    wire BO, D;

    Full_Subtractor m1(BO, D, X, Y, BI);

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
