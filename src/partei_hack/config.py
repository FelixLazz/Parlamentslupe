"""Zentrale Standardwerte; keine impliziten Netz- oder Schreibzugriffe."""

import os
from dataclasses import dataclass
from pathlib import Path

API_BASE_URL = "https://www.abgeordnetenwatch.de/api/v2/"
MIN_REQUEST_INTERVAL = 2.1
CACHE_TTL_SECONDS = 24 * 60 * 60
PAGE_SIZE = 1000


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @classmethod
    def resolve(cls, data_dir: Path | None = None) -> "Settings":
        root = data_dir or Path(os.environ.get("PARTEIHACK_DATA_DIR", "data"))
        return cls(data_dir=root.expanduser().resolve())

    @property
    def database_path(self) -> Path:
        return self.data_dir / "processed" / "parteihack.sqlite3"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"
