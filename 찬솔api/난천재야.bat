@echo off
echo =========================================
echo Q-Net 정보처리산업기사 자격증 정보 자동 다운로드 BAT
echo =========================================
echo ㅤ
echo 1. 쿠키 발급 cookies.txt
curl -c cookies.txt -X POST "https://q-net.or.kr/crf005.do?id=crf005" ^
-d "jmCd=2290&jmInfoDivCcd=B0&jmNm=정보처리산업기사" ^
-H "User-Agent: Mozilla/5.0" ^
-H "Referer: https://q-net.or.kr/crf005.do" ^
-o NUL
echo ㅤ
echo ㅤ
echo 2. 종목정보 jmDtail.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00505&gSite=Q&gId=&jmCd=2290&jmNm=정보처리산업기사&jobSearch=&gbnn=" -o jmDtail.html
echo ㅤ
echo ㅤ
echo 3. 시험정보(B0) exam_info.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00503s02&gSite=Q&gId=&jmCd=2290&jmInfoDivCcd=B0&jmNm=정보처리산업기사" -o exam_info.html
echo ㅤ
echo ㅤ
echo 4. 기본정보(A0) basic_info.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00503s01&gSite=Q&gId=&jmCd=2290&jmInfoDivCcd=A0&jmNm=" -o basic_info.html
echo ㅤ
echo ㅤ
echo 5. 우대현황(C0) privilege_info.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00503s03&gSite=Q&gId=&jmCd=2290&jmInfoDivCcd=C0&jmNm=" -o privilege_info.html
echo ㅤ
echo ㅤ
echo 6. 직업훈련정보(D0) job_training_info.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00503s04&gSite=Q&gId=&jmCd=2290&mapJmCd=5002290&jmNm=" -o job_training_info.html
echo ㅤ
echo ㅤ
echo 7. 수험자동향 (id=crf00503s06) trend_info.txt
echo ㅤ
curl -b cookies.txt "https://q-net.or.kr/crf005.do?id=crf00503s06&gSite=Q&gId=&examInstiCd=&jmCd=2290&mapJmCd=5002290&jmNm=" -o trend_info.html
echo ㅤ
echo ㅤ
echo 모든 파일 다운로드 완료
pause
