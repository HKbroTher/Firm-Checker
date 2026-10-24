"""保存每家企业最近一次生成的画像，避免重复调用 LLM。"""

import hashlib
from pathlib import Path

from .models import CompanyProfile


class ProfileHistory:
    def __init__(self, directory: Path):
        self.directory = directory

    def _path(self, company: str) -> Path:
        return self.directory / f"{hashlib.sha1(company.encode()).hexdigest()[:16]}.json"

    def save(self, profile: CompanyProfile) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path(profile.company).write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    def load(self, company: str) -> CompanyProfile | None:
        path = self._path(company)
        if not path.exists():
            return None
        return CompanyProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def delete(self, company: str) -> None:
        self._path(company).unlink(missing_ok=True)
