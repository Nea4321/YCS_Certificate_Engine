@echo off
setlocal enabledelayedexpansion

REM 쿠키 파일
set COOKIE_FILE=cookies.txt

REM 출력 디렉토리
set OUTPUT_DIR=exam_data
if not exist %OUTPUT_DIR% mkdir %OUTPUT_DIR%

REM 기관 코드 배열
set ORG_CODES=P200 R139 N004 P317 R121 N003 R020 N002

REM 각 기관 코드 순회
for %%C in (%ORG_CODES%) do (
    echo 처리 중: %%C
    REM curl POST 요청
    curl -s -b %COOKIE_FILE% -X POST "https://q-net.or.kr/crf005.do?id=crf00501s01&div=3&examInstiCd=%%C&qualgbCd=T" ^
         -H "User-Agent: Mozilla/5.0" ^
         -H "Referer: https://q-net.or.kr/crf005.do" ^
         -o "%OUTPUT_DIR%\%%C.txt"
)

echo 완료!
pause
