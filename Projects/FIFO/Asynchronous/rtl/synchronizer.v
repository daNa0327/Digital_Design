module synchronizer (
    input ck, // wr_ck or rd_ck
    input reset,

    input  [3:0] gray_ptr,
    output [3:0] gray_ptr_sync
);
    reg [3:0] ff1;
    reg [3:0] ff2;

    always @(posedge ck or posedge reset) begin
        if(reset) begin
            ff1 <= 4'b0000;
            ff2 <= 4'b0000;
        end
        else begin
            ff1 <= gray_ptr;
            ff2 <= ff1;
        end
    end

    assign gray_ptr_sync = ff2;
endmodule
