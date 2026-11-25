# tt_setup — 설치 도우미. 글자 인식 모델·무료 글꼴을 공개 주소에서 받고(파일마다 sha256 확인), 글꼴 목록을 만들고, 설치가 됐는지 점검한다.
#   python -X utf8 tools/tt_setup.py check          → 무엇이 있고 없는지 표로(설치 뒤 맨 끝에 돌림)
#   python -X utf8 tools/tt_setup.py ocr            → RapidOCR 한국어 인식 모델(약 24MB)
#   python -X utf8 tools/tt_setup.py fonts-free     → 무료·상업 사용 가능 글꼴 61개(fonts/free_fonts.json, 약 88MB)
#   python -X utf8 tools/tt_setup.py fonts-base     → 기본 후보 글꼴 7개(fonts/base_fonts.json — Windows에 없을 때)
#   python -X utf8 tools/tt_setup.py fonts-noonnu [목록.json]  → 눈누 공개 글꼴 묶음(fonts/noonnu_repos.json, 약 1,760개 · 1.7GB · 30분 넘게)
#   python -X utf8 tools/tt_setup.py fonts-index    → 눈누 묶음의 글꼴 목록(_cmap.json·_이름.json) 만들기 — 글꼴을 더 넣었으면 다시 돌림
#   python -X utf8 tools/tt_setup.py all            → 위를 차례로 다(check 까지)
# 받은 파일은 tt_config.py 가 정한 폴더(기본 ~/ThumbTitle_data)에 둔다. 이미 있고 sha256이 맞으면 다시 받지 않는다.
import hashlib, io, json, os, shutil, subprocess, sys, time, urllib.parse, urllib.request, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tt_config as CFG

ROOT = CFG.ROOT
UA = {"User-Agent": "Mozilla/5.0 (font-fetch)"}
OCR_FILES = [
    ("korean_PP-OCRv4_rec_mobile.onnx", "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/master/onnx/PP-OCRv4/rec/korean_PP-OCRv4_rec_mobile.onnx",
     "ab151ba9065eccd98f884cf4d927db091be86137276392072edd4f9d43ad7426"),
    ("korean_dict.txt", "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/korean_dict.txt",
     "aa1fdc8ae8f7cd40a0ec4edb472eb0421e11427e6ccfee9915440742c18b0a20"),
]
FONT_EXT = (".woff2", ".woff", ".ttf", ".otf")


def log(s): print(time.strftime("[%H:%M:%S] ") + s, flush=True)


def sha(b): return hashlib.sha256(b).hexdigest()


def get(url, tries=3):
    u = urllib.parse.quote(url, safe=":/@?=&%")
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=180) as r: return r.read()
        except Exception as e:
            if k == tries - 1: log(f"  받기 실패 {url}: {e}"); return None
            time.sleep(2 + 3 * k)


_ZIP = {}
def fetch(item):
    if item.get("zip"):
        if item["zip"] not in _ZIP:
            b = get(item["zip"]); _ZIP[item["zip"]] = zipfile.ZipFile(io.BytesIO(b)) if b else None
        z = _ZIP[item["zip"]]
        return z.read(item["member"]) if z else None
    return get(item["url"])


def put_list(listfile, dst):
    os.makedirs(dst, exist_ok=True)
    L = json.load(open(listfile, encoding="utf-8")); ok = bad = skip = 0
    for it in L:
        p = os.path.join(dst, it["file"])
        if os.path.exists(p) and (not it.get("sha256") or sha(open(p, "rb").read()) == it["sha256"]): skip += 1; continue
        b = fetch(it)
        if b is None: bad += 1; continue
        if it.get("sha256") and sha(b) != it["sha256"]:
            log(f"  sha256 다름 — 버림: {it['file']} (받는 곳 파일이 바뀐 듯)"); bad += 1; continue
        open(p, "wb").write(b); ok += 1
        if it.get("note"): log(f"  {it['file']}: {it['note']}")
    log(f"{os.path.basename(listfile)} → {dst}: 새로 {ok} · 이미 있음 {skip} · 실패 {bad} (모두 {len(L)})")
    return bad == 0


def ocr():
    os.makedirs(CFG.OCR_KO, exist_ok=True); good = True
    for name, url, h in OCR_FILES:
        p = os.path.join(CFG.OCR_KO, name)
        if os.path.exists(p) and sha(open(p, "rb").read()) == h: log(f"있음 {name}"); continue
        b = get(url)
        if not b or sha(b) != h: log(f"실패 {name} (sha256 다름 또는 못 받음)"); good = False; continue
        open(p, "wb").write(b); log(f"받음 {name} ({len(b)//1024}KB)")
    return good


def fonts_noonnu(lst=None):
    lst = lst or os.path.join(ROOT, "fonts", "noonnu_repos.json")
    r = subprocess.call([sys.executable, "-X", "utf8", os.path.join(HERE, "tt_fontpool.py"), lst, CFG.FONT_POOL])
    return r == 0


def fonts_index():
    pool = CFG.FONT_POOL
    if not os.path.isdir(pool): log(f"눈누 글꼴 폴더가 없음: {pool} — 먼저 fonts-noonnu"); return False
    paths = []
    for d, _, fs in os.walk(pool):
        for f in fs:
            if f.lower().endswith(FONT_EXT): paths.append(os.path.join(d, f).replace("\\", "/"))
    lst = os.path.join(CFG.TMP, "tt_fontpaths.txt"); open(lst, "w", encoding="utf-8").write("\n".join(sorted(paths)))
    log(f"글꼴 파일 {len(paths)}개 목록 만드는 중(_cmap.json)")
    r1 = subprocess.call([CFG.FONTTOOLS_PY, "-X", "utf8", os.path.join(HERE, "tt_fontcmap.py"), lst, os.path.join(pool, "_cmap.json")])
    r2 = subprocess.call([CFG.FONTTOOLS_PY, "-X", "utf8", os.path.join(HERE, "tt_fontnames.py"), pool])
    return r1 == 0 and r2 == 0


def check():
    rows = []
    def row(k, ok, v): rows.append((k, "됨" if ok else "안 됨", v))
    row("Python", sys.version_info[:2] in ((3, 11), (3, 12)), sys.version.split()[0] + " (3.11·3.12에서 시험함)")
    for m in ("numpy", "cv2", "PIL", "rapidocr_onnxruntime", "fontTools", "brotli"):
        try: __import__(m); row("패키지 " + m, True, "있음")
        except Exception as e: row("패키지 " + m, False, f"없음({e.__class__.__name__}) — pip install -r requirements.txt")
    sys.path.insert(0, HERE)
    import tt_typo as T
    row("Chrome", bool(T.CHROME), T.CHROME or "못 찾음 — Chrome 설치 또는 tt_config.json 의 chrome 칸")
    ok_ocr = all(os.path.exists(os.path.join(CFG.OCR_KO, n)) for n, _, _ in OCR_FILES)
    row("글자 인식 모델", ok_ocr, CFG.OCR_KO if ok_ocr else "없음 — tt_setup.py ocr")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                            "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]; "
                            "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag }"], capture_output=True, timeout=60)
        langs = r.stdout.decode("utf-8", "ignore").split()
        row("Windows 글자 인식(한국어)", any(l.lower().startswith("ko") for l in langs), ", ".join(langs) or "없음 — SETUP.md 4단계")
    except Exception as e: row("Windows 글자 인식(한국어)", False, f"확인 못 함({e.__class__.__name__})")
    n_extra = len([f for f in os.listdir(CFG.FONT_EXTRA)]) if os.path.isdir(CFG.FONT_EXTRA) else 0
    row("무료 글꼴(빠른 후보)", n_extra >= 61, f"{n_extra}개 / 61")
    base = [c for c in T.CANDS if T.font_path(c[1])]
    row("기본 후보 글꼴", len(base) >= len(T.CANDS) - 3, f"{len(base)}개 / {len(T.CANDS)} (맑은 고딕 등 — 없는 것: {', '.join(c[0] for c in T.CANDS if not T.font_path(c[1])) or '없음'})")
    cm = os.path.join(CFG.FONT_POOL, "_cmap.json")
    n_pool = len(json.load(open(cm, encoding="utf-8"))) if os.path.exists(cm) else 0
    row("눈누 글꼴 묶음(_cmap.json)", n_pool >= 1700, f"{n_pool}개 (만든 사람 PC 1,763개)")
    row("node(선택: 진행 감시)", bool(shutil.which("node")), shutil.which("node") or "없음 — 감시(tt_watchdog.mjs)만 못 씀")
    try:
        import tt_typo2 as T2
        row("남은 메모리", T2.free_mb() >= 3072, f"{T2.free_mb():.0f}MB (재현은 3,072MB 넘을 때까지 기다림)")
    except Exception as e: row("남은 메모리", False, str(e))
    print("| 점검 | 결과 | 값 |\n|---|---|---|")
    for k, s, v in rows: print(f"| {k} | {s} | {v} |")
    return all(s == "됨" for k, s, v in rows if not k.startswith(("node", "남은")))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    F = os.path.join(ROOT, "fonts")
    steps = {"ocr": ocr, "fonts-free": lambda: put_list(os.path.join(F, "free_fonts.json"), CFG.FONT_EXTRA),
             "fonts-base": lambda: put_list(os.path.join(F, "base_fonts.json"), CFG.FONT_BASE),
             "fonts-noonnu": lambda: fonts_noonnu(sys.argv[2] if len(sys.argv) > 2 else None), "fonts-index": fonts_index, "check": check}
    if cmd == "all":
        ok = True
        for k in ("ocr", "fonts-free", "fonts-base", "fonts-noonnu", "fonts-index", "check"):
            log(f"== {k}"); ok = steps[k]() and ok
        sys.exit(0 if ok else 1)
    if cmd not in steps: print(__doc__ or open(__file__, encoding="utf-8").read().split("import")[0]); sys.exit(2)
    sys.exit(0 if steps[cmd]() else 1)
