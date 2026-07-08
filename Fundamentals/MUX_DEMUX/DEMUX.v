module DEMUX_4to1 (OUT0, OUT1, OUT2, OUT3, IN, S0, S1);
    input IN, S0, S1;
    output OUT0, OUT1, OUT2, OUT3;

    assign OUT0 = IN & ~S0 & ~S1;
    assign OUT1 = IN & ~S0 &  S1;
    assign OUT2 = IN &  S0 & ~S1;
    assign OUT3 = IN &  S0 &  S1;
endmodule

module Top;

    wire OUT0, OUT1, OUT2, OUT3;
    reg IN, S0, S1;

    DEMUX_4to1 m1(OUT0, OUT1, OUT2, OUT3, IN, S0, S1);

    initial begin
        IN = 1;
        $display("IN = %d", IN);
        
        #1 S0 = 0; S1 = 0;
        $monitor("S0 = %d S1 = %d / OUT0 = %d OUT1 = %d OUT2 = %d OUT3 = %d", S0, S1, OUT0, OUT1, OUT2, OUT3);
        #1 S0 = 0; S1 = 1;
        #1 S0 = 1; S1 = 0;
        #1 S0 = 1; S1 = 1;
    end
endmodule
