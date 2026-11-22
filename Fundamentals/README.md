# Digital Design Fundamentals
기초적인 Verilog HDL 학습을 위한 논리회로 구현 모듈 저장소입니다.

각 회로는 RTL 설계, Testbench 작성, 시뮬레이션, 그리고 직접 작성한 진리표, 논리식, 회로도를 포함하여 학습 내용을 정리합니다.

## 📂 Directory Structure

```text
Fundamentals/
├── Encoder_Decoder/   # 인코더/디코더
├── MUX_DEMUX/         # 멀티플렉서/디멀티플렉서
├── Comparator/        # 비교기 (크기 비교)
├── Adder/             # 가산기 (Half Adder, Full Adder)
├── Subtractor/        # 감산기 (Half Subtractor, Full Subtractor)
├── Flip_Flop/         # 플립플롭 (D, JK, T 등 순차회로의 기본 소자)
├── Register/          # 레지스터 (데이터 저장, Shift Register)
├── Counter/           # 카운터 (동기/비동기 카운터)
└── README.md


└──Logic Circuit/
    ├── Logic Circuit.v            # RTL, testbench 파일
    ├── docs/                      # 직접 작성한 학습 자료
    │   └── Truth Table, Circuit Diagram, Logic Equation.png   # 진리표, 회로도, 논리식
    └── README.md
```