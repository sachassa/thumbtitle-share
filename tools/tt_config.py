# tt_config — 이 도구 묶음이 쓰는 폴더·프로그램 자리를 한 곳에서 정한다.
#   읽는 순서: 환경 변수 TT_* → 설정 파일(저장소 맨 위 tt_config.json, 또는 TT_CONFIG 가 가리키는 파일) → 기본값.
#   설정 파일 예: config.example.json 을 tt_config.json 으로 복사해 고친다. 아무것도 안 고치면 기본값으로 돈다.
#   확인: python -X utf8 tools/tt_config.py  → 지금 쓰는 값과 있는지/없는지를 찍는다.
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load():
    p = os.environ.get("TT_CONFIG") or os.path.join(ROOT, "tt_config.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8-sig"))
        except Exception as e:
            print(f"[tt_config] 설정 파일을 못 읽음({p}): {e} — 기본값으로 돈다", file=sys.stderr)
    return {}


_C = _load()


def _get(key, env, default):
    v = os.environ.get(env) or _C.get(key)
    return os.path.expanduser(str(v)).replace("\\", "/") if v else default


HOME = os.path.expanduser("~").replace("\\", "/")
DATA = _get("data_dir", "TT_DATA", HOME + "/ThumbTitle_data")                 # 글꼴·모델을 받아 둘 곳(수 GB)
FONT_POOL = _get("font_pool", "TT_FONT_POOL", DATA + "/fonts/noonnu")          # 눈누 공개 글꼴 묶음(약 1,760개 · 1.7GB)
FONT_EXTRA = _get("font_extra", "TT_FONT_EXTRA", DATA + "/fonts/thumbtitle")   # 무료 글꼴 61개(빠른 후보)
FONT_BASE = _get("font_base", "TT_FONT_BASE", DATA + "/fonts/base")            # 기본 후보 글꼴(Windows에 없으면 여기서 찾음)
GLYPH_CACHE = _get("glyph_cache", "TT_GLYPH_CACHE", DATA + "/fonts/_글자모양")  # 글자 모양 저장(자동으로 생김)
HFC_PREFER = _get("hfc_prefer", "TT_HFC_PREFER", DATA + "/fonts/hfc_prefer.json")  # 선택(없어도 됨)
OCR_KO = _get("ocr_model_dir", "TT_OCR_KO", DATA + "/models/ocr-ko")           # RapidOCR 한국어 인식 모델
TMP = _get("tmp_dir", "TT_TMP", tempfile.gettempdir().replace("\\", "/"))      # 잠깐 쓰는 파일
JOBS = _get("jobs_dir", "TT_JOBS", HOME + "/ThumbTitle_입구")                    # 입구로 돌린 작업 폴더들
FONTTOOLS_PY = _get("fonttools_python", "TT_FONTTOOLS_PY", sys.executable)    # fontTools 가 깔린 파이썬(기본 = 지금 파이썬)
CHROME = _get("chrome", "TT_CHROME", None)                                     # 비우면 흔한 설치 자리에서 찾음

os.makedirs(TMP, exist_ok=True)


def show():
    rows = [("data_dir", DATA), ("font_pool", FONT_POOL), ("font_extra", FONT_EXTRA), ("font_base", FONT_BASE),
            ("glyph_cache", GLYPH_CACHE), ("ocr_model_dir", OCR_KO), ("tmp_dir", TMP), ("jobs_dir", JOBS),
            ("fonttools_python", FONTTOOLS_PY), ("chrome", CHROME or "(자동으로 찾음)")]
    for k, v in rows:
        ok = "있음" if (v and os.path.exists(v)) else "없음"
        print(f"{k:17s} {v}  [{ok}]")


if __name__ == "__main__":
    show()
