module bin2gray (
    input  [3:0] bin_ptr,
    output [3:0] gray_ptr
);
    /*
    assign gray_ptr[3] = bin_ptr[3];
    assign gray_ptr[2] = bin_ptr[3] ^ bin_ptr[2];
    assign gray_ptr[1] = bin_ptr[2] ^ bin_ptr[1];
    assign gray_ptr[0] = bin_ptr[1] ^ bin_ptr[0];
    */
    assign gray_ptr = bin_ptr ^ (bin_ptr >> 1);
endmodule
