module sec_counter ( // 00 ~ 59 -> 00 + 1 
    input ck,
    input reset,
    output reg [5:0] sec,
    output reg carry
);
    always @(posedge ck) begin
        if(reset) begin // Reset
            sec <= 0;
            carry <= 0;
        end
        else if(sec == 59) begin
            sec <= 0;
            carry <= 1;
        end
        else begin
            sec <= sec + 1;
            carry <= 0;
        end
    end
endmodule


module min_counter ( // 00 ~ 59 -> 00 + 1
    input ck,
    input reset,
    input sec_carry,
    output reg [5:0] min,
    output reg carry
);
    always @(posedge ck) begin
        if(reset) begin // Reset
            min <= 0;
            carry <= 0;
        end
        else if(sec_carry) begin // if sec_carry == 1: every 60 sec
            if(min == 59) begin
                min <= 0;
                carry <= 1;
            end
            else begin
                min <= min + 1;
                carry <= 0;
            end
        end
        else begin
            carry <= 0;
        end
    end
endmodule


module hour_counter ( // 00 ~ 23 -> 00 
    input ck,
    input reset,
    input min_carry,
    output reg [4:0] hour
);
    always @(posedge ck) begin
        if(reset) begin // Reset
            hour <= 0;
        end
        else if(min_carry) begin // if min_carry == 1: every 60 min
            if(hour == 23) begin
                hour <= 0;
            end
            else begin
                hour <= hour + 1;
            end
        end
    end
endmodule
