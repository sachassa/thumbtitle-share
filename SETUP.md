# 설치 안내 — AI가 그대로 따라 하는 순서

이 문서는 사람이 아니라 **AI(Claude Code·Codex 등)가 위에서부터 그대로 따라 하도록** 썼습니다. 단계마다 「칠 명령」 → 「확인 명령」 → 「기대 결과」가 있습니다. 기대 결과가 안 나오면 다음 단계로 가지 말고 그 단계를 고칩니다.
명령은 저장소 맨 위 폴더에서 PowerShell로 칩니다. 다 깔고 나면 [CLAUDE.md](CLAUDE.md)대로 일합니다.

## 0. 준비물

| 항목 | 필요한 것 | 까닭 |
|---|---|---|
| OS | **Windows 10/11 (64비트)** | Windows 글자 인식(winocr.ps1)·메모리 재기(Windows API)를 씀. macOS·Linux는 시험하지 않음 |
| Python | **3.11** (3.12도 될 것으로 봄 — 시험은 3.11) | rapidocr-onnxruntime 1.4.4 가 3.13 이상을 받지 않음 |
| Chrome | Google Chrome(아무 판) | 재현 그림을 Chrome 화면 없이 찍음 |
| Node.js | 선택(있으면 진행 감시 `tt_watchdog.mjs`를 씀) | 없어도 재현은 됨 |
| 메모리 | 남은 메모리 **3GB 이상**(8GB PC면 다른 프로그램을 닫음) | 3GB 아래면 재현 프로그램이 기다림 |
| 디스크 | 약 **3GB** (글꼴 1.8GB + 글자 모양 저장 약 0.2GB + 프로그램 약 0.5GB) | |
| 인터넷 | 설치 때 글꼴·모델 받기, 쓸 때 공개 썸네일 받기 | 로그인·API 키 없음 |

## 1. Python 가상 환경과 패키지

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

확인:
```powershell
.\.venv\Scripts\python.exe -c "import numpy, cv2, PIL, rapidocr_onnxruntime, fontTools, brotli; print('패키지 됨')"
```
기대 결과: `패키지 됨`. (`py -3.11` 이 없으면 python.org 에서 Python 3.11 64비트를 깔고 다시.)

패키지 목록(`requirements.txt`, tools/*.py 의 import 를 훑어 만든 것):

| 패키지 | 쓰는 곳 |
|---|---|
| numpy · opencv-python-headless | 그림 계산·겹침 재기 |
| pillow | 글자 그리기, 그림 열기 |
| onnxruntime · rapidocr-onnxruntime | 글자 읽기(RapidOCR) |
| fonttools · brotli | 글꼴 안 글자표·이름 읽기(woff2 는 brotli 필요) |

이 뒤로 `python` 은 모두 `.\.venv\Scripts\python.exe` 를 뜻합니다.

## 2. 폴더 자리 정하기(선택)

기본값으로 두면 받은 글꼴·모델은 `~/ThumbTitle_data/`, 작업 결과는 `~/ThumbTitle_입구/` 에 생깁니다. 바꾸려면:

```powershell
Copy-Item config.example.json tt_config.json   # 그리고 tt_config.json 의 칸을 고침(비운 칸 = 기본값)
```
환경 변수로도 됩니다(설정 파일보다 먼저): `TT_DATA`(글꼴·모델 둘 곳), `TT_JOBS`(작업 결과), `TT_FONT_POOL`, `TT_FONT_EXTRA`, `TT_FONT_BASE`, `TT_OCR_KO`, `TT_TMP`, `TT_CHROME`, `TT_FONTTOOLS_PY`, `TT_CONFIG`(설정 파일 자리).

확인:
```powershell
.\.venv\Scripts\python.exe -X utf8 tools/tt_config.py
```
기대 결과: 칸 10줄이 찍힘(아직 받기 전이라 「없음」이 많은 것이 정상).

## 3. 글자 인식 모델(약 24MB, 1분 안팎)

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py ocr
```
받는 곳: RapidOCR 모델 저장소(ModelScope `RapidAI/RapidOCR`, PP-OCRv4 한국어 인식 모델 · Apache 2.0)와 PaddleOCR 한국어 글자표. 파일마다 sha256 을 확인합니다.
기대 결과: `받음 korean_PP-OCRv4_rec_mobile.onnx`, `받음 korean_dict.txt`.

## 4. Windows 글자 인식(한국어) 켜기

두 번째 글자 읽기 프로그램입니다. 확인:
```powershell
powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | % LanguageTag"
```
기대 결과: 목록에 `ko` 또는 `ko-KR` 이 있음. 없으면(관리자 PowerShell 에서, 사람에게 관리자 승인을 부탁):
```powershell
Add-WindowsCapability -Online -Name "Language.OCR~~~ko-KR~0.0.1.0"
```
없어도 재현은 돌지만 글자 읽기가 한 가지로만 되어 틀릴 가능성이 커집니다.

## 5. 글꼴 받기

글꼴 파일은 이 저장소에 없습니다. **무료이고 다시 받아도 되는 공개 주소에서만** 자동으로 받고, 파일마다 sha256 이 만든 사람 PC의 파일과 같은지 확인합니다(같지 않으면 버림).

| 순서 | 명령 | 무엇 | 크기·시간(실측) |
|---|---|---|---|
| 5-1 | `.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py fonts-free` | 빠른 후보 글꼴 61개 — 목록 `fonts/free_fonts.json` (눈누 웹폰트 저장소 jsDelivr, Google Fonts 저장소, Pretendard npm, SUIT, 네이버 한글 글꼴, 원티드·배민·고도 공식 배포) | 약 88MB · 몇 분 |
| 5-2 | `.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py fonts-base` | 기본 후보 글꼴(검은고딕·도현·주아·나눔명조·나눔고딕·Noto Sans KR) — Windows에 없을 때 쓰려고 받아 둠. 목록 `fonts/base_fonts.json` | 약 30MB |
| 5-3 | `.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py fonts-noonnu` | 눈누(noonnu.cc) 공개 글꼴 묶음 — GitHub `projectnoonnu` 저장소 138곳, 판 고정(`fonts/noonnu_repos.json`) | 약 1,760개 · 1.7GB · 30분 넘게(인터넷 빠르기에 따라) |
| 5-4 | `.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py fonts-index` | 눈누 묶음의 글꼴 목록 만들기(`_cmap.json` 글자표, `_이름.json` 이름) — 글꼴을 더 넣었으면 다시 돌림 | 몇 분 |

확인: `.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py check` → 「무료 글꼴 61개 / 61」, 「눈누 글꼴 묶음 1,7xx개」.

글꼴 이용 조건:

| 글꼴 | 받는 법 | 비용 | 상업 사용 |
|---|---|---|---|
| `fonts/free_fonts.json` 61개 | 자동(5-1) | 무료 | 대부분 가능(SIL OFL 또는 만든 곳의 무료 조건). 썸네일에 실제로 쓰기 전에 각 만든 곳의 조건을 다시 확인 |
| 눈누 묶음 | 자동(5-3) | 무료 | 눈누는 상업 무료 글꼴만 싣지만 글꼴마다 조건이 다름 — 여기서는 원본 글꼴 알아내기·비교에만 쓰고, 실제로 쓸 글꼴은 그 글꼴 쪽 조건을 따로 확인 |
| 맑은 고딕 | Windows에 들어 있음 | — | Windows 조건 |
| 나눔고딕 Bold·ExtraBold, Noto Sans KR | 자동(5-2) | 무료(OFL) | 가능. 단 만든 사람 PC와 **판이 다름**(같은 판의 공개 주소를 못 찾음) — 이 글꼴로 맞춘 결과는 조금 다를 수 있음 |
| KoPub돋움·바탕 Bold, 은돋움 | 자동으로 받지 않음 | 무료 | 원하면 각 배포처에서 받아 `font_base` 폴더(기본 `~/ThumbTitle_data/fonts/base`)에 같은 파일 이름(`KoPubDotumBold.ttf`, `KoPubBatangBold.ttf`, `UnDotum.ttf`)으로 넣음. 없으면 그 후보만 빠짐 |
| 유료 글꼴·산돌구름 글꼴(예: Sandoll 격동고딕) | **사람이 직접**, 자기 계정·약관대로 | 유료 또는 가입 | 각 약관. 파일을 받을 수 있는 글꼴만 `font_extra` 폴더(기본 `~/ThumbTitle_data/fonts/thumbtitle`)에 넣음. 산돌구름처럼 파일을 주지 않는 곳은 못 씀. AI는 대신 로그인·결제·사이트 자동 조작을 하지 않음 |

글꼴이 없으면 이렇게 됩니다: 그 글꼴로 만든 썸네일은 「글꼴 못 찾은 줄: …」로 끝나고 판정은 「일치 안 됨(글꼴 없음)」입니다. 다른 글꼴로 대신 그려 일치라고 하지 않습니다.

## 6. 설치 점검

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/tt_setup.py check
```
기대 결과: 표의 모든 줄이 「됨」(node·남은 메모리 줄은 「안 됨」이어도 설치는 끝난 것).

## 7. 돌려 보기 — 입구 시험 3건

입구 명령 하나로 받기 → 글자 읽기·글꼴 찾기·맞추기 → 정밀 맞춤 → 검수·색 겹침 → 화면 만들기까지 갑니다. 한 번에 한 편만.

```powershell
# ① 그림 파일 하나(jpg·png·webp, 받은 크기 그대로 씀)
.\.venv\Scripts\python.exe -X utf8 tools/tt_entry.py "C:\경로\썸네일.jpg"
# ② 쇼츠 주소(세로 표지 oardefault 를 받음)
.\.venv\Scripts\python.exe -X utf8 tools/tt_entry.py "https://www.youtube.com/shorts/<영상 번호>"
# ③ 롱폼 주소(maxresdefault → sddefault → hqdefault 순)
.\.venv\Scripts\python.exe -X utf8 tools/tt_entry.py "https://www.youtube.com/watch?v=<영상 번호>"
```
기대 결과: 화면에 `[   0.6초] 받기 — 끝 · 쇼츠 · https://i.ytimg.com/...` 처럼 단계마다 한 줄이 찍히고, 마지막에 `== 끝: 100% 일치 — 비교 화면: ...\비교.html` 또는 `== 끝: 일치 안 됨 — ...`. 작업 폴더 `~/ThumbTitle_입구/<날짜시각>_<번호>/` 에 `비교.html`·`입구_진행.json`·`그림/`·`값/`.
걸리는 시간: 한 편에 몇 분~20분(줄 수·글자 수·PC에 따라 — 실제는 `입구_진행.json`의 `경과초`).
실패하면 쉬운 말로 까닭이 찍힙니다(주소 틀림 · 썸네일 없음 · 글자 없음 · 글꼴 못 찾음 · 시간 초과). 뜻과 할 일은 CLAUDE.md 5절.

## 8. 화면 켜기(편집·입구 화면)

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/tt_editor.py "<결과 폴더>"
```
그리고 브라우저로 **http://127.0.0.1:8765/최종.html** 을 엽니다. 메인 화면을 이렇게 `tt_editor.py <결과 폴더>` 로 켜고 이 주소로 열어야 「+ 신규 영상 등록」(그림 끌어 놓기·주소 칸·시작 단추·진행 상태)이 동작합니다. `비교.html` 파일을 그냥 더블클릭해 열면 보기만 되고 등록은 안 됩니다.
`<결과 폴더>` = `최종.html` 이 있는 폴더. 이 저장소에 든 예: `.\.venv\Scripts\python.exe -X utf8 tools/tt_editor.py 타이틀재현_3판` → http://127.0.0.1:8765/최종.html . 입구 작업 폴더 하나(`~/ThumbTitle_입구/<날짜시각>_<번호>`)를 주면 그 결과를 고쳐 보는 편집 화면(http://127.0.0.1:8765/)이 됩니다. 결과 폴더 없이 `tools/tt_editor.py` 만 쳐도 켜지며, 이때는 입구 작업 폴더(`jobs_dir`)를 봅니다.
확인: `curl http://127.0.0.1:8765/jobs` → `[...]`(입구로 돌린 작업 목록, JSON). 끄기 = Ctrl+C. 이 화면은 이 PC 안(127.0.0.1)에서만 열립니다.

## 9. DB·수집 자료

입구(그림 하나·주소 하나)는 **DB 없이** 돕니다. 만든 사람 쪽의 수집 DB(collect.sqlite 등)는 싣지 않으며, 필요하지 않습니다.
여러 편을 한꺼번에 보고 싶으면 주소를 하나씩 입구에 넣습니다(한 번에 한 편). 썸네일은 공개 주소 `https://i.ytimg.com/vi/<영상 번호>/<maxresdefault|sddefault|hqdefault|oardefault>.jpg` 에서 한 장씩만 받고, 영상·소리는 받지 않습니다. 많이 받을 때는 사람 속도로(한 장에 몇 초 띄워) 받습니다.

## 10. 더 받을 수 있는 것(선택)

| 무엇 | 쓰임 | 크기·시간 | 지금 |
|---|---|---|---|
| PaddleOCR 전체·LaMa(그림 메우기) | 글자 읽기·배경 메우기를 더 좋게 | 수백 MB~수 GB | 이 도구는 쓰지 않음(설치 안 해도 됨) |
| Node.js | 진행 감시(`tools/tt_watchdog.mjs`) | 약 30MB | 선택 |

## 11. 지킬 것

- 남의 썸네일은 이 PC 안에서 비교·연구용으로만. 생성 AI 재료로 넘기지 않고, 웹에 공개하지 않고, 글꼴 찾기 사이트에 올리지 않습니다.
- 글꼴은 각 이용 조건대로. 글꼴 파일을 다시 나눠 주지 않습니다.
- 비밀값(API 키·토큰)·`tt_config.json`(자기 PC 경로)을 저장소에 올리지 않습니다(`.gitignore` 에 있음).

## 12. 이 안내가 어디까지 시험됐나(2026-11-25, 만든 사람 PC의 빈 폴더에서)

| 단계 | 상태 | 근거 |
|---|---|---|
| 1. venv·패키지 설치(Python 3.11, requirements.txt) | 확인됨 | 실측 — 설치 뒤 import 6개 됨. 처음엔 requirements.txt 의 한글 주석을 pip 가 cp949 로 읽어 실패 → 주석을 영어로 고침 |
| 2. 설정(tt_config.json 으로 폴더 옮기기) | 확인됨 | 실측 — tt_config.py 가 바꾼 폴더를 찍음 |
| 3. 글자 인식 모델 받기 | 확인됨 | 실측 — 2개 파일 sha256 일치 |
| 5-1·5-2 무료 글꼴 61개·기본 글꼴 7개 받기 | 확인됨 | 실측 — 실패 0. 61개는 만든 사람 PC 파일과 sha256 같음, 기본 글꼴 중 3개(나눔고딕 Bold·ExtraBold, Noto Sans KR)는 판이 다름 |
| 5-3 눈누 묶음 받기(1.7GB) | 진행 중이었음(끝까지 확인 안 됨) | 실측 — 138곳 가운데 59곳까지 실패 없이 받음 |
| 5-4 글꼴 목록 만들기 | 아직 확인 안 됨 | 5-3 이 끝나야 돌림 |
| 8. 화면 켜기(tt_editor.py) | 확인됨 | 실측 — 결과 폴더 없이 켜서 `/`·`/jobs` 응답 200 |
| 8. 최종.html 의 「+ 신규 영상 등록」 | 아직 확인 안 됨 | 화면 쪽을 막 고치는 중이었음 |
| 7. 입구 시험 3건(그림·쇼츠 주소·롱폼 주소) | 아직 확인 안 됨 | 글꼴 묶음이 다 받아진 뒤 돌릴 차례였음 |
| 같은 결과가 나오는지(최종 2편 중 한 장) | 아직 확인 안 됨 | 위와 같음 |
