module Decoder_2to4(OUT0, OUT1, OUT2, OUT3, IN0, IN1);

    input IN0, IN1;
    output OUT0, OUT1, OUT2, OUT3;

    assign OUT0 = ~IN0 & ~IN1;
    assign OUT1 = ~IN0 &  IN1;
    assign OUT2 =  IN0 & ~IN1;
    assign OUT3 =  IN0 &  IN1;
endmodule

module Top;

    wire OUT0, OUT1, OUT2, OUT3;
    reg IN0, IN1;

    Decoder_2to4 m1(OUT0, OUT1, OUT2, OUT3, IN0, IN1);

    initial begin
        #1 IN0 = 0; IN1 = 0;
        $monitor("IN0 = %d IN1 = %d / OUT0 = %d OUT1 = %d OUT2 = %d OUT3 = %d", IN0, IN1, OUT0, OUT1, OUT2, OUT3);
        #1 IN0 = 0; IN1 = 1;
        #1 IN0 = 1; IN1 = 0;
        #1 IN0 = 1; IN1 = 1;
    end
endmodule
