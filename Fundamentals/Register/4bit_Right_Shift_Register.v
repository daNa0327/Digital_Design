module bit4_Right_Shift_Register(
    output reg [3:0] Q,
    input SI, // Serial Input
    input CK
);
    initial Q = 4'b0101; // 초기 Q를 0101으로 설정
        
    always @(posedge CK) begin
        Q <= { SI, Q[3:1] };
        /* Q[3] <= SI
           Q[2] <= Q[3]
           Q[1] <= Q[2]
           Q[0] <= Q[1] */
    end
endmodule

module Top;

    reg SI;
    reg CK;
    wire [3:0] Q;

    bit4_Right_Shift_Register m1(Q, SI, CK);
    
    always #1 CK = ~CK;
    
    initial begin
        CK = 0; SI = 0;

        $monitor("CK = %b / SI = %b / Q = %b", CK, SI, Q);

        #2 SI = 1;
        #2 SI = 0;
        #2 SI = 1;
        #2 SI = 1;
        #2 SI = 0;

        #1 $finish();
    end
endmodule
