module Half_Adder (C, S, A, B);

    input A, B;
    output C, S;

    assign C = A & B;
    assign S = A ^ B;
endmodule

module Top;

    wire CO, CH1, CH2, SH;
    reg A, B, CI;

    Half_Adder m1(CH1, SH, A, B);
    Half_Adder m2(CH2, S, SH, CI);
    
    assign CO = CH1 | CH2;

    initial begin
        #1 A = 0; B = 0; CI = 0;
        $monitor("A = %d B = %d CI = %d / CO = %d S = %d", A, B, CI, CO, S);
        #1 A = 0; B = 0; CI = 1;
        #1 A = 0; B = 1; CI = 0;
        #1 A = 0; B = 1; CI = 1;
        #1 A = 1; B = 0; CI = 0;
        #1 A = 1; B = 0; CI = 1;
        #1 A = 1; B = 1; CI = 0;
        #1 A = 1; B = 1; CI = 1;
    end
endmodule
