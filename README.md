# YCS Certificate **Engine** (Python)

> 자격증 공개/사설 정보를 크롤링·정규화해서 **JSON 산출물**을 만드는 파이썬 엔진입니다.  
> 이 문서는 **`Crawling/Certificate/Engine` 루트**에서 사용하는 기준으로 작성되었습니다.

---

## 폴더 구성(요약)

```
Engine/
 ├─ public_cert_api/           # Q-Net(공개) 파이프라인: fetch/parse/normalize 러너
 ├─ private-cert-crawl/        # 사설(학교/민간) 크롤러 모음
 ├─ normalizer_min_v1          # 정규화 패키지(모듈로 실행)
 ├─ tools/
 │   └─ export_certs.py        # DB에서 certificate_id, jmcd, name → certs.csv 내보내기
 ├─ scripts/
 │   └─ engine_bootstrap       # (선택) 의존성 설치 도우미
 ├─ .gitignore / requirements.txt / README.md / run_once.py ...
```

---

## 1) 빠른 시작 (공개 Q-Net 정규화만 돌려보기)

### A. 필수 요건
- **Python 3.11+**
- **Chrome 최신 버전** (Selenium이 자동으로 ChromeDriver를 맞춰줍니다)
- (Windows) PowerShell 또는 Git Bash

### B. 가상환경 & 의존성
```bash
python -m venv .venv

# Windows
. ./.venv/Scripts/Activate.ps1
# macOS/Linux
source ./.venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### C. 입력 데이터 준비
정규화 러너는 **탭별 HTML 또는 파싱된 JSON**이 있는 루트를 요구합니다. 예시 구조:

```
C:\cert-data\chansol_api\1320\
  ├─ basic_info.html.gz
  ├─ exam_info.html.gz
  ├─ preference.html.gz
  └─ (정규화 결과는 같은 폴더에 생성)
```

> 스냅샷 모드(`--mode snapshot`)에서는 **fetch 단계를 건너뛰고** 위 파일들을 바로 parse/normalize 합니다.

### D. 단일 종목만 실행(예: 정보처리기사 `1320`)
```powershell
# 상대경로 예시(Engine 루트에서 상위의 cert-data 폴더를 기준으로 잡기)
$BASE = Resolve-Path ..\..\..            # => C:\cert-data
$ROOT = Join-Path $BASE 'chansol_api'    # => C:\cert-data\chansol_api

python -m public_cert_api.run_public `
  --root "$ROOT" `
  --jmcd 1320 `
  --mode snapshot `
  --steps parse,normalize `
  --force `
  --display-name "정보처리기사"
```

### E. 여러 종목 일괄 실행
`targets.txt`에 JMCD를 한 줄에 하나씩 넣고 실행합니다.
```text
1320
0370
0752
```
```powershell
python -m public_cert_api.run_public `
  --root "$ROOT" `
  --list C:\cert-data\targets.txt `
  --mode snapshot `
  --steps parse,normalize `
  --resume
```

### F. 산출물
실행 후 각 종목 폴더 안에 다음이 생깁니다.

- `{jmcd}.json` : 파싱 중간 산출물
- `{jmcd}.norm.json` : **최종 정규화 결과**
- `norm_trace.json` : 정규화 **추적/근거(trace)** (검수용)
- `issues.jsonl`(루트): 종목별 이슈(경고/누락) 기록

> `exam_method.errors`에 `phase_none_payload`만 있고 다른 필드가 정상이라면 **콘텐츠 자체가 없었던 케이스**로 간주하며 실패가 아닙니다.

---

## 2) certificate_id 매핑(선택)

정규화 산출물의 `_meta.certificate_id`를 채우고 싶다면 **`tools/export_certs.py`**로 CSV를 만듭니다.

### A. .env 템플릿(팀 내부 DB 접속이 가능한 경우만 사용)
> **중요**: `.env`는 절대 커밋하지 않습니다.

```
# .env.example  (이 파일만 공개 저장소에 커밋)
DB_HOST=your-db-host.example.com
DB_PORT=your_port
DB_NAME=your_db_name
DB_USERNAME=your_db_user
DB_PASSWORD=your_secure_password

# (선택) 한 줄 URL로 쓰고 싶다면
# DB_URL=jdbc:postgresql://HOST:PORT/DBNAME

```

### B. CSV 내보내기
```bash
# Engine 루트에서
python tools/export_certs.py
```
- 기본 출력: `Engine/out/certs.csv`
- 환경변수 `CERT_EXPORT_CSV`로 경로를 바꿀 수 있습니다.

### C. 정규화 결과에 주입
`certs.csv`를 만들어 두면 러너가 `_meta.certificate_id`를 자동 패치합니다.

```powershell
$BASE = Resolve-Path ..\..\..
$ROOT = Join-Path $BASE 'chansol_api'
$CSV  = Join-Path $PWD  'out\certs.csv'   # Engine/out/certs.csv

python -m public_cert_api.run_public `
  --root "$ROOT" `
  --csv  "$CSV" `
  --jmcd 1320 `
  --mode snapshot `
  --steps normalize `
  --force
```
> CSV 없이도 실행은 됩니다. 이 기능은 **certificate_id/name을 `_meta`에 보강**하고 싶을 때만 사용하세요.

---

## 3) 사설(민간/학교) 크롤러

`private-cert-crawl/` 이하의 크롤러는 **크롤링 → JSON 저장**까지 담당합니다.  
공유 저장소에서는 `.env`를 제공하지 않으므로, 팀 외부에서는 **DB 내보내기 기능은 비활성**로 간주하세요.

### 공통 실행(예시)
```bash
python run_once.py --cert linux_master --config private-cert-crawl\configs\cert_map.yaml 
# 산출물은 기본적으로 Engine/data/ 아래 생성
```

Spring에서 소비하려면 결과 JSON을 **Spring 프로젝트의 `src/main/resources/json/`**로 복사하세요.

---

## 4) 커밋/배포 가이드

- **커밋 금지**: `.env`, `.venv/`, `__pycache__/`, 크롤링 캐시, 대용량 산출물(선택)  
- 팀원 설치 절차
  1) 저장소 클론 → 2) 가상환경 생성/활성화 → 3) `pip install -r requirements.txt`
- **윈도우 PowerShell**에서는 줄바꿈용 백틱(`)을, **bash**에서는 `\`을 사용하세요.
- `python -m package.module` 형태로 실행(상대 import 오류 방지)

---

## 5) 자주 보는 오류 & 해결

- `ImportError: attempted relative import with no known parent package`  
  → 모듈 루트에서 **`python -m public_cert_api.run_public`** 같이 `-m` 사용.

- `ModuleNotFoundError: No module named 'psycopg2'`  
  → DB 내보내기 기능을 쓰는 경우에만 필요합니다. `pip install -r requirements.txt` 확인.

- 경로 인식 문제(Windows)  
  → PowerShell의 **따옴표**와 **백틱 줄바꿈**을 확인.  
  → 예: `--root "C:\cert-data\chansol_api"` 처럼 전체를 따옴표로 감쌉니다.

---

## 6) 라이선스
프로젝트 루트의 `LICENSE` 파일을 따릅니다.
