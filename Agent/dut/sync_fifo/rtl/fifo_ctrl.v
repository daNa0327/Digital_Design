module fifo_ctrl(
    input ck,
    input reset,

    input wr_en,
    input rd_en,

    output reg [2:0] wr_ptr,
    output reg [2:0] rd_ptr,

    output full,
    output empty
);
    reg [3:0] count; // 0 ~ 8 // 0 : empty // 8 : full 

    assign empty = (count == 0);
    assign full  = (count == 8);

    always @(posedge ck or posedge reset) begin
        if (reset) begin
            wr_ptr  <= 0;
            rd_ptr  <= 0;
            count   <= 0;
        end
        else begin
            case ({wr_en, rd_en})
                // Pass
                2'b00: begin
                end
                // Read
                2'b01: begin
                    if (!empty) begin
                        rd_ptr <= rd_ptr + 1;
                        count  <= count - 1;
                    end
                end
                // Write
                2'b10: begin
                    if (!full) begin
                        wr_ptr <= wr_ptr + 1;
                        count  <= count + 1;
                    end
                end
                // Write + Read
                2'b11: begin
                    // 둘다 수행
                    if (!empty && !full) begin
                        wr_ptr <= wr_ptr + 1;
                        rd_ptr <= rd_ptr + 1;
                    end
                    // FIFO가 비어있다면 Write만 수행
                    else if (empty) begin
                        wr_ptr <= wr_ptr + 1;
                        count  <= count + 1;
                    end
                    // FIFO가 꽉 찼다면 Read만 수행
                    else if (full) begin
                        rd_ptr <= rd_ptr + 1;
                        count  <= count - 1;
                    end
                end
            endcase
        end
    end

endmodule
