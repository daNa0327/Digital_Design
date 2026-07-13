/*  IDLE 상태에서는 tx=1, busy=0이며 tx_start 신호를 기다린다. 
    tx_start가 입력되면 START 상태로 전이하여 Start bit(tx=0)를 출력하고 busy=1이 된다. 
    이후 baud_tick이 발생할 때마다 DATA 상태에서 8비트를 LSB부터 순차적으로 전송한다. 
    8비트 전송이 끝나면 STOP 상태에서 Stop bit(tx=1)를 출력하고, 
    마지막 baud_tick 이후 busy=0으로 변경한 뒤 IDLE 상태로 복귀한다.
*/

/*  Idle   Start   Data       Stop   Idle
    11111  0       10110101   1      11111
tx: 11111 0 10101101 1 11111
*/
module UART_TX (
    input ck,
    input reset,
    input baud_tick,
    input tx_start,
    input tx_data[7:0],

    output tx,
    output busy
);

endmodule
