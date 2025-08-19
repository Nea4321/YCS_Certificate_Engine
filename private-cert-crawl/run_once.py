# run_once.py
import argparse, importlib, json, yaml
from pathlib import Path
from typing import Iterable, Optional
from schemas.v1 import RootV1, MetaV1
import inspect
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 이 파일(run_once.py)이 위치한 폴더 경로
ROOT = Path(__file__).parent


def _make_driver(headless: bool = True):
    """Selenium Chrome WebDriver 생성 (동적 렌더링 필요 시 사용)."""
    opts = Options()
    # opts.add_argument("--headless=new")  # 필요시 활성화
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,2000")
    return webdriver.Chrome(options=opts)


def _call_runner(fn):
    """
    runner 호출 헬퍼.
    - 시그니처가 ()면 fn() 호출
    - 첫 인자가 driver면 WebDriver를 만들어 fn(driver) 호출
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    if not params:
        return fn()
    if params[0] == "driver":
        driver = _make_driver(headless=True)
        try:
            return fn(driver)
        finally:
            driver.quit()
    raise TypeError("runner는 인자 없이 호출되거나 첫번째 인자가 driver여야 합니다.")


def load_cfg():
    """configs/cert_map.yaml 읽어 dict로 반환."""
    with open(ROOT / "configs" / "cert_map.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def import_callable(spec: str):
    """
    "모듈경로:속성" 형태의 spec을 로드해 호출 가능한 객체를 반환.
    - 함수면 그대로 반환
    - 클래스/인스턴스면 .normalize 메서드가 있으면 그 메서드 반환
    """
    mod_name, attr = spec.split(":")
    mod = importlib.import_module(mod_name)
    obj = getattr(mod, attr)

    if callable(obj) and getattr(obj, "__name__", None) != "__init__":
        return obj  # 함수 등

    # 클래스/인스턴스 지원
    inst = obj() if isinstance(obj, type) else obj
    if hasattr(inst, "normalize") and callable(inst.normalize):
        return inst.normalize

    raise TypeError(f"Unsupported callable spec: {spec}")


def default_output_for(cert: str) -> Path:
    """자격증별 기본 저장 경로 생성."""
    return ROOT / cert / "data" / f"{cert}_full.json"


def _pick_tabs(cfg_tabs: list[dict], wanted: Optional[Iterable[str]]):
    """
    실행 대상 탭 선별.
    - wanted가 None/빈값이면 config 탭 전체 반환
    - 그렇지 않으면 name 매칭되는 탭만 필터링
    """
    if not wanted:
        return cfg_tabs
    wanted_set = {t.strip() for t in wanted}
    return [t for t in cfg_tabs if t["name"] in wanted_set]


def run(cert: str, tabs: Optional[Iterable[str]] = None, out: Optional[str] = None):
    """
    실행 파이프라인(수집 → 정규화 → 검증 → 저장).
    - cert: 자격증 키 (cert_map.yaml의 certifications 하위 키)
    - tabs: 실행할 탭 이름들의 이터러블 (없으면 전체)
    - out : 출력 경로 (없으면 기본 경로)
    """
    cfg = load_cfg()
    cert_cfg = cfg["certifications"].get(cert)
    if not cert_cfg:
        raise SystemExit(f"unknown cert: {cert}")

    sel_tabs = _pick_tabs(cert_cfg["tabs"], tabs)

    # 최종 JSON 뼈대 구성
    root = {
        "_meta": MetaV1(cert=cert).model_dump(),  # 메타데이터(자격증 식별 등)
        "시험일정": None,
        "시험내용": None,
    }

    # 각 탭별로 runner → normalizer 실행 후 섹션 채우기
    for t in sel_tabs:
        run_fn = import_callable(t["runner"])
        norm_fn = import_callable(t["normalizer"])
        raw = _call_runner(run_fn)     # 원시 데이터 수집
        section = norm_fn(raw)         # V1 스키마 형태(dict)로 정규화
        root[t["target"]] = section    # 대상 섹션에 삽입

    # V1 스키마로 최종 검증(형/필수 필드/구조 안전장치)
    RootV1.model_validate(root)

    # 출력 경로 준비 후 저장
    out_path = Path(out) if out else default_output_for(cert)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(root, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✔ saved: {out_path}")


def _infer_cert_from_cwd(cfg) -> Optional[str]:
    """
    작업 디렉토리 이름을 cert 키로 추론.
    - 현재 폴더명이 certifications에 존재하면 그 키 반환, 아니면 None
    """
    cwd = Path.cwd().name
    return cwd if cwd in cfg.get("certifications", {}) else None


def main():
    """CLI 진입점: 인자 파싱 → cert 결정 → run 실행."""
    p = argparse.ArgumentParser(
        prog="cert-crawler",
        description="자격증 탭 크롤러 (runner → normalizer → v1 validate → save)"
    )
    p.add_argument("--cert", help="예: digital_information (미지정시 현재 작업폴더명으로 추론)")
    p.add_argument("--out", help="와 생각도 못했다")
    # 간단 버전: --tabs/--out 생략. 필요해지면 add_argument로 확장.
    args = p.parse_args()

    cfg = load_cfg()
    cert = args.cert or _infer_cert_from_cwd(cfg)
    if not cert:
        raise SystemExit("cert를 알 수 없습니다. --cert 지정 또는 자격증 폴더에서 실행하세요")
    
    out = args.out or default_output_for(cfg)
    if not out:
         raise SystemExit("out을 알 수 없습니다. --cert 지정 또는 자격증 폴더에서 실행하세요")

    run(cert=cert,out=out)  # tabs/out은 기본값 사용


if __name__ == "__main__":
    main()
