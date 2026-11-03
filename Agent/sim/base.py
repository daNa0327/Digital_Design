from abc import ABC, abstractmethod

from core.models import RunResult

class Simulator(ABC):
    # Agent가 아는 유일한 시뮬레이터 인터페이스.
    @abstractmethod
    def run(self, files: list[str], top: str, workdir: str) -> RunResult:
        ...