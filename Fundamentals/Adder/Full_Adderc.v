module Full_Adder (CO, S, A, B, CI);

    input A, B, CI;
    output CO, S;

    assign CO = ((A ^ B) & CI) | (A & B);
    assign S = A ^ B ^ CI;
endmodule

module Top;

    wire CO, S;
    reg A, B, CI;

    Full_Adder m1(CO, S, A, B, CI);

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
