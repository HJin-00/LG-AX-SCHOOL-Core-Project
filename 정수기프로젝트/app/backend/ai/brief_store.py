"""E가 실제 생성한 파일을 서버 내부에서 등록. 외부 등록 API는 없다."""
from pathlib import Path
import re


class BriefStore:
    def __init__(self, root: Path, max_files=1000):
        self.root = root.resolve()
        self.max_files = max_files
        self._files: dict[str, tuple[str, Path]] = {}

    def register(self, brief_id: str, path: str | Path, session_id: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", brief_id):
            raise ValueError("잘못된 준비서 ID")
        target = Path(path).resolve(strict=True)
        if not target.is_relative_to(self.root) or not target.is_file() or target.suffix not in {".md", ".txt", ".pdf"}:
            raise ValueError("허용한 준비서 경로가 아닙니다.")
        if brief_id in self._files:
            raise ValueError("이미 등록된 준비서 ID")
        if len(self._files) >= self.max_files:
            raise ValueError("준비서 등록 용량 초과")
        self._files[brief_id] = (session_id, target)

    def resolve(self, brief_id: str, session_id: str) -> Path | None:
        record = self._files.get(brief_id)
        if record is None or record[0] != session_id:
            return None
        try:
            path = record[1].resolve(strict=True)
        except OSError:
            return None
        if not path.is_relative_to(self.root) or not path.is_file():
            return None
        return path
