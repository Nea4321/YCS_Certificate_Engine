# normalizers/v1_core/build/config_loader.py
from __future__ import annotations
import re, yaml
from importlib.resources import files as pkg_files
from pathlib import Path

__all__ = ["load_schedule_config", "classify_from_yaml"]

# normalizers/v1_core/build/config_loader.py

def _to_rx(words):
    if not words:
        return None
    # 토큰 내부 공백을 제거한 형태로 매칭 (헤더는 이미 norm()에서 공백 제거됨)
    normed = [re.escape((w or "").replace(" ", "")) for w in words]
    return re.compile("|".join(normed))


def _load_yaml():
    try:
        cfg_path = pkg_files("public_cert_api.normalizers.v1_core.configs") / "schedule_headers.yaml"
        print("[CFG] from", cfg_path)
        with cfg_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        local = Path(__file__).resolve().parents[1] / "configs" / "schedule_headers.yaml"
        with open(local, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

def load_schedule_config():
    cfg = _load_yaml()

    # row-phase 감지
    row_phase_tokens = cfg.get("row_phase_tokens", [])
    row_phase_rx = {p: re.compile(re.escape(p)) for p in row_phase_tokens}

    # 필드 헤더 매핑
    fields = cfg["fields"]
    rx = {
        "회차": _to_rx(fields["회차"]),
        "접수기간": {
            "neutral": _to_rx(fields["접수기간"].get("neutral")),
            "필기":    _to_rx(fields["접수기간"].get("필기")),
            "실기":    _to_rx(fields["접수기간"].get("실기")),
        },
        "추가접수기간": _to_rx(fields["추가접수기간"]["any"]),
        "서류제출기간": _to_rx(fields["서류제출기간"]["any"]),
        "의견제시기간": _to_rx(fields["의견제시기간"]["any"]),
        "시험일": {
            "neutral": _to_rx(fields["시험일"].get("neutral")),
            "필기":    _to_rx(fields["시험일"].get("필기")),
            "실기":    _to_rx(fields["시험일"].get("실기")),
            "면접":    _to_rx(fields["시험일"].get("면접")),
        },
        "발표": {
            "neutral": _to_rx(fields["발표"].get("neutral")),
            "필기":    _to_rx(fields["발표"].get("필기")),
            "실기":    _to_rx(fields["발표"].get("실기")),
        },
    }

    # ✅ 배너/안내행 규칙
    bcfg = cfg.get("banner_row", {}) or {}
    banners = {
        "contains_any": _to_rx(bcfg.get("contains_any")),
        "first_cell_contains": _to_rx(bcfg.get("first_cell_contains")),
        "first_cell_excludes": _to_rx(bcfg.get("first_cell_excludes")),
        "min_dates_in_row": int(bcfg.get("min_dates_in_row") or 0),
    }

    return row_phase_rx, rx, banners  # ← 반환값 확장

def classify_from_yaml(h_norm: str, _: dict, rx: dict):
    if rx["회차"] and rx["회차"].search(h_norm):
        return None, "회차"

    # 접수기간
    for ph in ("필기","실기"):
        r = rx["접수기간"].get(ph)
        if r and r.search(h_norm):
            return ph, "접수기간"
    if rx["접수기간"]["neutral"] and rx["접수기간"]["neutral"].search(h_norm):
        return None, "접수기간"

    # 서류/의견제시
    for k in ("서류제출기간","의견제시기간"):
        if rx[k] and rx[k].search(h_norm):
            return None, k

    # 시험일
    for ph in ("필기","실기","면접"):
        r = rx["시험일"].get(ph)
        if r and r.search(h_norm): return ph, "시험일"
    if rx["시험일"]["neutral"] and rx["시험일"]["neutral"].search(h_norm):
        return None, "시험일"

    # 발표
    for ph in ("필기","실기"):
        r = rx["발표"].get(ph)
        if r and r.search(h_norm): return ph, "발표"
    if rx["발표"]["neutral"] and rx["발표"]["neutral"].search(h_norm):
        return None, "발표"

    return None, None
