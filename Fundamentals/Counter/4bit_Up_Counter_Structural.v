module T_FF (
    output reg Q,
    input T,
    input CK
);
    initial Q = 1'b0; // 초기 Q를 0으로 설정

    always @(posedge CK) begin
        Q <= T ? ~Q : Q;    // T = 0: Hold, 1: Toggle 
    end
endmodule

module bit4_UP_Counter ( // Structural Counter
    output [3:0] Q,
    input CK
);
    wire q0, q1, q2, q3;
    wire T0, T1, T2, T3;

    assign T0 = 1'b1;
    assign T1 = q0;
    assign T2 = q1 & q0;
    assign T3 = q2 & q1 & q0;

    T_FF m0(q0, T0, CK);
    T_FF m1(q1, T1, CK);
    T_FF m2(q2, T2, CK);
    T_FF m3(q3, T3, CK);

    assign Q = {q3, q2, q1, q0};
endmodule

module Top;

    reg CK;
    wire [3:0] Q;

    bit4_UP_Counter m1(Q, CK);
    
    always #1 CK = ~CK;
    
    initial begin
        CK = 0;

        $monitor("CK = %b / Q = %b", CK, Q);

        #32 $finish;
    end
endmodule
