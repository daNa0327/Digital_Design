module T_FF (
    output reg Q,
    input T,
    input CK
);

initial begin // 초기 Q를 0으로 설정
    Q = 0;
end

always @(posedge CK) begin
    Q <= T ? ~Q : Q;    // T = 0: Hold, 1: Toggle 
end

endmodule

module Top;
    reg T, CK;
    wire Q;

    always #1 CK = ~CK;

    T_FF m1(Q, T, CK);

    initial begin
        CK = 0;
        T = 0;

        $monitor("CK = %b / T = %b / Q = %b", CK, T, Q);

        #3 T = 1;   // Toggle
        #3 T = 0;   // Hold
        #3 T = 1;   // Toggle
        #3 T = 0;   // Hold
        
        #1 $finish;
    end
endmodule
