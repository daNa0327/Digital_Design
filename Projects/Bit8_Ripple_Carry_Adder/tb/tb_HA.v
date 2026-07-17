`timescale 1ns / 1ps

module tb_HA();
    reg A;
    reg B;
    wire C;
    wire S;
    
    HA dut (
        .A(A), 
        .B(B), 
        .C(C), 
        .S(S)
    );

    initial begin
        A = 0; B = 0;
        #100;
        A = 0; B = 1;
        #100;
        A = 1; B = 0;
        #100;
        A = 1; B = 1;
        #100;
        $stop;
    end
    
endmodule
