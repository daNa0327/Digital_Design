module fifo_ctrl (
    input wr_ck,
    input rd_ck,
    input reset,

    input wr_en,
    input rd_en,

    output reg [3:0] wr_ptr,
    output reg [3:0] rd_ptr,

    output reg full,
    output reg empty
);
    wire [3:0] wr_gray;
    wire [3:0] rd_gray;

    bin2gray wr_gray1(
        .bin_ptr(wr_ptr),
        .gray_ptr(wr_gray)
    );

    bin2gray rd_gray1(
        .bin_ptr(rd_ptr),
        .gray_ptr(rd_gray)
    );

    wire [3:0] wr_gray_sync;
    wire [3:0] rd_gray_sync;

    synchronizer sync_rd2wr(
        .ck(wr_ck),
        .reset(reset),
        .gray_ptr(rd_gray),
        .gray_ptr_sync(rd_gray_sync)
    );

    synchronizer sync_wr2rd(
        .ck(rd_ck),
        .reset(reset),
        .gray_ptr(wr_gray),
        .gray_ptr_sync(wr_gray_sync)
    );

    wire [3:0] wr_ptr_next;
    wire [3:0] wr_gray_next;
    assign wr_ptr_next = wr_ptr + (wr_en && !full);

    bin2gray wr_gray2(
        .bin_ptr(wr_ptr_next),
        .gray_ptr(wr_gray_next)
    );

    always @(posedge wr_ck or posedge reset) begin
        if (reset) begin
            wr_ptr <= 0;
            full   <= 0;
        end
        else begin
            if (wr_en && !full) begin
                wr_ptr <= wr_ptr + 1;
            end

            full <= (wr_gray_next == {
                    ~rd_gray_sync[3],
                    ~rd_gray_sync[2],
                     rd_gray_sync[1],
                     rd_gray_sync[0]});
        end
    end

    always @(posedge rd_ck or posedge reset) begin
        if (reset) begin
            rd_ptr <= 0;
            empty  <= 1;
        end
        else begin
            if (rd_en && !empty) begin
                rd_ptr <= rd_ptr + 1;
            end

            empty <= (wr_gray_sync == rd_gray);
        end
    end
endmodule
