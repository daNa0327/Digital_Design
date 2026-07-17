`timescale 1ns / 1ps

module tb_bit8_Adder();
    reg [7:0] A;
    reg [7:0] B;

    wire C;
    wire [7:0] S;

    /*  integer i;
        integer j; */

    bit8_Adder dut (
        .A(A),
        .B(B),

        .C(C),
        .S(S)
    );

    initial begin
        A = 8'b11111111; B = 8'b11111111;
        #100;
        A = 8'b11110000; B = 8'b00101011;
        #100;
        A = 8'b00110011; B = 8'b11001100;
        #100;
        A = 8'b10110101; B = 8'b01000101;
        #100;
        /*  for (i = 0; i < 32; i=i+1) begin
                for (j = 0; j < 32; j=j+1) begin
                    A = i; B = j;
                    #10;
                end
            end */
        $stop;
    end

endmodule
