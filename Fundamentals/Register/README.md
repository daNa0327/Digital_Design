# Register / Shift Register
Verilog HDL로 4-bit Register와 4-bit Right Shift Register를 설계했습니다.

Register는 여러 bit를 한 번에 저장하고, Shift Register는 클럭마다 저장된 값을 한 칸씩 이동합니다.

## 📁 Files
| File | Description | Modeling |
|---|---|---|
| `4bit_Register.v` | 4-bit Parallel Load Register + Testbench | Behavioral |
| `4bit_Right_Shift_Register.v` | 4-bit Right Shift Register (Serial In) + Testbench | Behavioral |

## 1. 4-bit Register
클럭 상승 에지에서 4-bit 입력 D를 그대로 Q에 저장합니다. (D Flip-Flop 4개를 병렬로 묶은 구조)

```verilog
always @(posedge CK) begin
    Q <= D;
    /*  Q[3] <= D[3]
        Q[2] <= D[2]
        Q[1] <= D[1]
        Q[0] <= D[0] */
end
```

## 2. 4-bit Right Shift Register
Serial Input(SI)을 MSB에 넣고, 나머지 bit는 한 칸씩 LSB 방향으로 이동합니다.

```verilog
always @(posedge CK) begin
    Q <= { SI, Q[3:1] };
    /*  Q[3] <= SI
        Q[2] <= Q[3]
        Q[1] <= Q[2]
        Q[0] <= Q[1] */
end
```
초기값 `Q = 0101`에서 SI = 0, 1, 0, 1, 1을 차례로 입력했을 때 예상 동작:

| 클럭 | SI | Q |
|:-:|:-:|:-:|
| 초기 | - | 0101 |
| 1 | 0 | 0010 |
| 2 | 1 | 1001 |
| 3 | 0 | 0100 |
| 4 | 1 | 1010 |
| 5 | 1 | 1101 |

## 3. Register vs Shift Register
| 구분 | Register | Shift Register |
|---|---|---|
| 입력 | 4-bit 병렬 (D) | 1-bit 직렬 (SI) |
| 동작 | 한 번에 저장 | 한 칸씩 이동 |
| 용도 | 데이터 저장 | 직렬 ↔ 병렬 변환, 지연 |

## ✅ Key Learning
- 비차단 할당(`<=`)으로 모든 bit가 동시에 갱신되는 레지스터 동작
- Shift Register에서 이전 값(Q)을 이용해 연결(`{SI, Q[3:1]}`)하는 방법
- 직렬 입력이 4클럭 뒤 전체에 채워지는 시리얼 → 패럴렐 변환 개념 (UART, SPI의 기반)

## 🛠 Development Environment
- Verilog HDL / Antigravity IDE (VS Code)