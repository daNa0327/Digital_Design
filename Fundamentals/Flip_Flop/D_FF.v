module D_FF (
    output reg Q,
    input D,
    input CK
);

always @(posedge CK) begin
    Q <= D; // D의 값을 Q에 저장
    // = : 순서대로 대입
    // <= : 동시에 대입
end

endmodule

module Top;

    reg D, CK;
    wire Q;

    always #1 CK = ~CK;

    D_FF m1(Q, D, CK);

    initial begin
        CK = 0;
        D = 0;

        $monitor("%0t CK %b D = %b / Q = %b", $time, CK, D, Q);

        #3 D = 1;
        #3 D = 0;
        #3 D = 1;
        #3 D = 0;
        
        #1 $finish;
    end
endmodule
