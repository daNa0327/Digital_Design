module MUX_4to1 (OUT, IN0, IN1, IN2, IN3, S0, S1);

    input IN0, IN1, IN2, IN3, S0, S1;
    output OUT;

    assign OUT = (~S0 & ~S1 & IN0) |
                 (~S0 &  S1 & IN1) |
                 ( S0 & ~S1 & IN2) |
                 ( S0 &  S1 & IN3);
endmodule

module Top;
    
    wire OUT;
    reg IN0, IN1, IN2, IN3, S0, S1;

    MUX_4to1 m1(OUT, IN0, IN1, IN2, IN3, S0, S1);

    initial begin
        IN0 = 1; IN1 = 0; IN2 = 1; IN3 = 0;
        $display("IN0 = %d IN1 = %d IN2 = %d IN3 = %d", IN0, IN1, IN2, IN3);
        
        #1 S0 = 0; S1 = 0;
        $monitor("S0 = %d S1 = %d / OUT = %d", S0, S1, OUT);
        #1 S0 = 0; S1 = 1;
        #1 S0 = 1; S1 = 0;
        #1 S0 = 1; S1 = 1;
    end
endmodule
