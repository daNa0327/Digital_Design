# Asynchronous First In First Out
Verilog HDL을 활용하여 Ascynchronous FIFO(비동기식 FIFO)를 설계한 프로젝트입니다.

## Sync FIFO 와 Async FIFO의 차이
동기식의 경우 Write와 Read가 같은 Clock을 사용한다.
따라서 CDC(Clock Domain Crossing) 문제가 없다.
반면에 비동기식의 경우 서로 다른 Clock을 사용한다.

신호가 한 클락 도메인에서 다른 클락 도메인으로 건너갈 때 적절한 동기화 과정이 없으면 Metastability 문제가 발생한다.

Binary Code의 경우 0111 → 1000 여기서 4bit가 동시에 바뀐다.
반면에 Gray Code의 경우 0100 → 1100 처럼 항상 1bit만 변경된다.
따라서 CDC에서 매우 안전하다.
```text
*CDC : 서로 다른  Clock으로 동작하는 Clock Domain끼리 데이터를 전송하는 과정
*Metastability : 서로 다른 클럭 영역 간에 신호가 전달될 때 수신 측 플립플롭이 셋업/홀드 타임을 위반하여 출력이 '0'이나 '1'이 아닌 불안정한 중간 전압 상태에 빠지는 현상
*Binary Code Ex : 000 001 010 011 100 101 110 111
*Gray Code Ex : 000 001 011 010 110 111 101 100
```

## 🛠 Development Environment
- Language : Verilog HDL
- Editor : Antigravity IDE (VS Code)
- Tool : Vivado 2024.2
