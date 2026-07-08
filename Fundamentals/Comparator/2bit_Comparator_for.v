module bit2_Comparator(
    output G, L, E,
    input [1:0] A,
    input [1:0] B );

    assign G = (A[1] & ~B[1]) | (~(A[1]^B[1]) & (A[0] & ~B[0]));
    assign L = (~A[1] & B[1]) | (~(A[1]^B[1]) & (~A[0] & B[0]));
    assign E = ~(A[1]^B[1]) & ~(A[0]^B[0]);
endmodule

module Top;

    wire G, L, E;
    reg [1:0] A, B;

    bit2_Comparator m1(G, L, E, A, B);

    initial begin
        $monitor("A = %b B = %b / G = %b L = %b E = %b", A, B, G, L, E);

        for(integer i=0; i<4; i=i+1) begin
            for(integer j=0; j<4; j=j+1) begin
                #1 A = i[1:0]; B = j[1:0];
            end
        end
    end
endmodule
