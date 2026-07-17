`timescale 1ns / 1ps

module tb_FA();
    reg A;
    reg B;
    reg Ci;
    wire C;
    wire S;
    
    FA dut (
        .A(A),
        .B(B),
        .Ci(Ci),
        .C(C),
        .S(S)
    );

    initial begin
        A = 0; B = 0; Ci = 0;
        #100;
        A = 0; B = 0; Ci = 1;
        #100;
        A = 0; B = 1; Ci = 0;
        #100;
        A = 0; B = 1; Ci = 1;
        #100;
        A = 1; B = 0; Ci = 0;
        #100;
        A = 1; B = 0; Ci = 1;
        #100;
        A = 1; B = 1; Ci = 0;
        #100;
        A = 1; B = 1; Ci = 1;
        #100;
        $stop;
    end

endmodule
