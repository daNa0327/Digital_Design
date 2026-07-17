`timescale 1ns / 1ps

module tb_bit4_Adder();
    reg [3:0] A;
    reg [3:0] B;

    wire C;
    wire [3:0] S;

    /*  integer i;
        integer j; */

    bit4_Adder dut (
        .A(A),
        .B(B),

        .C(C),
        .S(S)
    );

    initial begin
        A = 8'b1111; B = 8'b1111;
        #100;
        A = 8'b0000; B = 8'b1111;
        #100;
        A = 8'b1001; B = 8'b1110;
        #100;
        A = 8'b0101; B = 8'b1101;
        #100;
        /*  for (i = 0; i < 16; i=i+1) begin
                for (j = 0; j < 16; j=j+1) begin
                    A = i; B = j;
                    #10;
                end
            end */
        $stop;
    end

endmodule
