module Encoder_4to2 (OUT0, OUT1, IN0, IN1, IN2, IN3);

    input IN0, IN1, IN2, IN3;
    output OUT0, OUT1;

    assign OUT0 = IN2 | IN3;
    assign OUT1 = IN1 | IN3;
endmodule

module Top;

    wire OUT0, OUT1;
    reg IN0, IN1, IN2, IN3;

    Encoder_4to2 m1(OUT0, OUT1, IN0, IN1, IN2, IN3);

    initial begin
        #1 IN0 = 1; IN1 = 0; IN2 = 0; IN3 = 0;
        $monitor("IN0 = %d IN1 = %d IN2 = %d IN3 = %d / OUT0 = %d OUT1 = %d", IN0, IN1, IN2, IN3, OUT0, OUT1);
        #1 IN0 = 0; IN1 = 1; IN2 = 0; IN3 = 0;
        #1 IN0 = 0; IN1 = 0; IN2 = 1; IN3 = 0;
        #1 IN0 = 0; IN1 = 0; IN2 = 0; IN3 = 1;
    end
endmodule
