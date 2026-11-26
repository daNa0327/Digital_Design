// I2C Master + Slave를 한 모듈로 묶은 평가용 top (spi_system과 같은 이유: top을 하나로 정하기 위함).
// SDA는 open-drain + pull-up을 wired-AND로 모델링한다: 누군가 당기면 0, 아무도 당기지 않으면 1.
// (tri-state/pullup 대신 이 방식을 쓰는 이유: Z 값 없이 xsim/Icarus에서 같은 결과를 내고 VCD에서 읽기 쉽다)
module i2c_system(
    input ck,                       // 50MHz
    input reset,                    // 비동기, active high
    input start,
    input rw,                       // 0: write, 1: read
    input [6:0] addr,

    input  [7:0] master_tx_data,
    input  [7:0] slave_tx_data,
    output [7:0] master_rx_data,
    output [7:0] slave_rx_data,

    output SCL,
    output SDA,
    output busy,
    output done,
    output ack_error
);
    wire m_sda_low;
    wire s_sda_low;

    assign SDA = ~(m_sda_low | s_sda_low);

    Master u_master (
        .ck(ck),
        .reset(reset),
        .start(start),
        .rw(rw),
        .addr(addr),

        .tx_data(master_tx_data),
        .rx_data(master_rx_data),

        .SCL(SCL),
        .sda_in(SDA),
        .sda_low(m_sda_low),

        .busy(busy),
        .done(done),
        .ack_error(ack_error)
    );

    Slave u_slave (
        .ck(ck),
        .reset(reset),
        .SCL(SCL),
        .sda_in(SDA),
        .sda_low(s_sda_low),

        .tx_data(slave_tx_data),
        .rx_data(slave_rx_data)
    );
endmodule
