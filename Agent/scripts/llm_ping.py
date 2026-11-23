"""LLM 연결 확인: 모델 목록 조회, 짧은 호출 한 번, 남은 일일 호출 수 출력.

사용:
    python -m scripts.llm_ping --list-models        # 이 키로 쓸 수 있는 모델 이름 (모델 설정 전에 실행)
    python -m scripts.llm_ping                       # RVA_LLM_MODEL로 호출 한 번 (캐시 사용 안 함)
    python -m scripts.llm_ping --prompt "안녕"
"""

import argparse
import sys

from llm.base import LLMError, LLMRequest
from llm.config import ConfigError, LLMConfig, load_env, make_client, make_provider


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-models", action="store_true", help="사용 가능한 모델 이름 출력")
    ap.add_argument("--prompt", default="Reply with the single word: pong")
    a = ap.parse_args(argv)

    load_env()
    try:
        if a.list_models:
            provider = make_provider(LLMConfig.from_env())
            for name in provider.list_models():
                print(name)
            return 0
        client = make_client(use_cache=False)
        resp = client.generate(LLMRequest(prompt=a.prompt, max_output_tokens=64))
    except (ConfigError, LLMError) as e:
        print(f"실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(f"모델: {resp.model}")
    print(f"응답: {resp.text.strip()[:200]}")
    print(f"토큰: 입력 {resp.input_tokens} / 출력 {resp.output_tokens}   지연: {resp.latency_s:.2f}s   종료: {resp.finish_reason}")
    if client.limiter is not None:
        print(f"오늘 남은 호출(설정 상한 기준): {client.limiter.remaining_today()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
