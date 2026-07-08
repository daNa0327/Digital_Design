module bit4_ALU ( // Arithmetic Logic Unit
    input [3:0] A, B,
    input [2:0] Op,
    output reg [3:0] Q,
    output reg Carry
);
    parameter ADD = 3'b000;
    parameter SUB = 3'b001;
    parameter AND = 3'b010;
    parameter OR = 3'b011;
    parameter XOR = 3'b100;
    parameter NOTA = 3'b101;
    parameter SHLA = 3'b110;
    parameter SHRA = 3'b111;

    always @(*) begin
        case (Op)
            ADD: begin
                {Carry, Q} = A + B;
            end
            SUB: begin
                Q = A - B;
                Carry = 0;
            end
            AND: begin
                Q = A & B;
                Carry = 0;
            end
            OR: begin
                Q = A | B;
                Carry = 0;
            end
            XOR: begin
                Q = A ^ B;
                Carry = 0;
            end
            NOTA: begin
                Q = ~A;
                Carry = 0;
            end
            SHLA: begin
                Q = A << 1;
                Carry = A[3];
            end
            SHRA: begin
                Q = A >> 1;
                Carry = A[0];
            end
            default: begin
                Q = 4'b0000;
                Carry = 1'b0;
            end
        endcase
    end
endmodule
