`timescale 1ns/1ps

module bit4_ALU_tb;

    reg [3:0] A, B;
    reg [2:0] Op;

    wire [3:0] Q;
    wire Carry;

    bit4_ALU DUT (
        .A(A),
        .B(B),
        .Op(Op),
        .Q(Q),
        .Carry(Carry)
    );

    initial begin

        $dumpfile("sim/wave.vcd");
        $dumpvars(0, bit4_ALU_tb);
        $monitor("Op = %b A = %b B = %b / Carry = %b Q = %b", Op, A, B, Carry, Q);

        #10 A = 4'd3; B = 4'd2; Op = 3'b000; // ADD
        #10 A = 4'd15; B = 4'd1; Op = 3'b000; // ADD (Carry)

        #10 A = 4'd8; B = 4'd3; Op = 3'b001; // SUB 
        #10 A = 4'd3; B = 4'd5; Op = 3'b001; // SUB (Negative Result)

        #10 A = 4'b1010; B = 4'b1100; Op = 3'b010; // AND
        #10 A = 4'b1010; B = 4'b1100; Op = 3'b011; // OR
        #10 A = 4'b1010; B = 4'b1100; Op = 3'b100; // XOR
        #10 A = 4'b1010; Op = 3'b101; // NOT

        #10 A = 4'b1001; Op = 3'b110; // Shift Left
        #10 A = 4'b1001; Op = 3'b111; // Shift Right

        #10 $finish;

    end

endmodule
