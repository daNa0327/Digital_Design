# Digital Design Projects
Verilog HDL을 활용하여 설계한 디지털 회로 프로젝트 저장소입니다.

각 프로젝트는 RTL 설계, Testbench 작성, 시뮬레이션 및 파형 분석, 결과 검증까지의 과정을 포함합니다.

## 📂 Directory Structure
```text
Projects/
├── ALU/                         # 산술 논리 연산 장치 (Arithmetic Logic Unit)
├── 8-bit_Ripple_Carry_Adder/    # 8비트 리플 캐리 가산기 (Full Adder 8개 연결)
├── Digital_Clock/               # 디지털 시계 (시/분/초 카운터)
├── Traffic_Light/               # 신호등 제어기 (FSM 기반)
├── UART/                        # 직렬 통신 프로토콜 (비동기 TX/RX)
├── SPI/                         # 직렬 통신 프로토콜 (동기, Master/Slave)
├── FIFO/                        # FIFO 메모리 (Sync FIFO, Async FIFO)
├── I2C/                         # 직렬 통신 프로토콜 (2선식, SDA/SCL)
└── README.md


└──Circuit/
    ├── rtl/                     # 합성 가능한 RTL 설계 파일
    │   └── Circuit.v
    ├── tb/                      # Testbench (시뮬레이션 전용)
    │   └── Circuit_tb.v
    ├── sim/                     # 시뮬레이션 결과
    │   ├── sim.out              # 시뮬레이션 실행 파일 (Icarus Verilog 컴파일 결과)
    │   ├── sim.png              # 시뮬레이션 로그/결과 캡처
    │   ├── wave.vcd             # 파형 덤프 파일 (GTKWave로 확인)
    │   └── wave.png             # 파형 캡처
    ├── docs/                    # 설계 문서
    │   └── Block Diagram, FSM, Schematic.png   # 블록 다이어그램, FSM, 회로도
    └── README.md
```