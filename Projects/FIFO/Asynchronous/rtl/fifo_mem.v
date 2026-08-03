module fifo_mem (
    input wr_ck,
    input rd_ck,
    
    input wr_en,
    input rd_en,

    input [2:0] wr_addr,
    input [2:0] rd_addr,

    input [7:0] data_in,
    output reg [7:0] data_out
);
    reg [7:0] mem [0:7]; // 8-bit x 8 memory

    always @(posedge wr_ck) begin
        if (wr_en) begin
            mem[wr_addr] <= data_in;
        end
    end

    always @(posedge rd_ck) begin
        if (rd_en) begin
            data_out <= mem[rd_addr];
        end
    end
endmodule
