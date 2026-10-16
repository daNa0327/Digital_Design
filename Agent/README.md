## Architecture
```
[RTL 파일]
   ↓
[1. RTL Analyzer]      포트/파라미터/FSM 추출 (LLM + 정규식)
   ↓
[2. TB Generator]      LLM이 self-checking TB 생성
   │                   (TB는 [TB] PASS / [TB] FAIL 출력 규약 강제)
   ↓
[2.5 Compile Gate]     xvlog 문법 검사 (결정적)
   │                   실패 시 에러 메시지와 함께 2번으로 되돌려 재시도 (최대 N회)
   ↓
[3. Simulator Tool]    xvlog → xelab → xsim -tclbatch run.tcl
   │                   → sim.log, dump.vcd  (결정적)
   │                   ※ Simulator 추상 클래스 + XsimSim 어댑터로 격리
   ↓
[4. Log Analyzer]      xsim 로그 파싱 → 공통 SimResult(JSON)로 변환 (결정적)
   │                   PASS/FAIL, 에러 라인, ERROR/FATAL_ERROR, 타임아웃 판정
   ↓ FAIL일 때만
[5. Debug Agent Loop]  ← 핵심 Agent 구간 (LLM + Tool Use, 최대 반복 제한)
     ├ get_log_snippet   로그 일부 조회
     ├ list_signals      계층/신호 목록 조회
     ├ read_vcd_signal   VCD에서 신호·시간 구간만 조회
     ├ read_rtl          RTL 해당 구간 읽기
     ├ 원인 가설 → 검증
     ├ propose_fix       수정 제안(diff), ★적용은 사람 승인 후★
     └ rerun_sim         runs/ 복사본에서만 재시뮬
   ↓
[6. Regression / Report]  결과 누적, Markdown 리포트
                          컴파일 성공률 / 버그 탐지율 / 원인 위치 정확도 / 평균 반복 횟수 등
```