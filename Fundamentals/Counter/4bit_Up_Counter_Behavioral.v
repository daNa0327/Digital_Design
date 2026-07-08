module bit4_UP_Counter ( // Behavioral Counter
    output reg [3:0] Q,
    input CK
);
    initial Q = 4'b0000; // 초기 Q를 0000으로 설정

    always @(posedge CK) begin
        Q <= Q + 1;
    end
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
