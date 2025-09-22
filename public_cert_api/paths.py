# public_cert_api/paths.py
from __future__ import annotations
from pathlib import Path
import os

# .../Engine/public_cert_api/paths.py → parents[1] = .../Engine
BASE_DIR = Path(__file__).resolve().parents[1]

def get_data_root() -> Path:
    """
    CERT_DATA_DIR 환경변수가 있으면 그 경로를 사용.
    없으면 기존 기본 경로(Engine/data) 사용.
    """
    override = os.getenv("CERT_DATA_DIR")
    if override:
        return Path(override)
    return BASE_DIR / "data"

DATA_DIR = get_data_root()
RAW_DIR  = DATA_DIR / "chansol_api"
LOG_DIR  = DATA_DIR / "_logs"
ERR_DIR  = DATA_DIR / "_errors"

# 필요하면 최초 import 시 폴더 생성
for p in (DATA_DIR, RAW_DIR, LOG_DIR, ERR_DIR):
    p.mkdir(parents=True, exist_ok=True)
