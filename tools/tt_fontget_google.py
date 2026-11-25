# tt_fontget_google — Google Fonts 공개 저장소(github.com/google/fonts, OFL = 상업 사용 가능)의 한글 글꼴을 받는다. 이미 있으면 건너뜀.
#   python -I tt_fontget_google.py <받을 폴더>
import json, os, sys, time, urllib.request, urllib.parse
FAMS = ["notosanskr", "notoserifkr", "nanumgothic", "nanummyeongjo", "nanumpenscript", "nanumbrushscript", "nanumgothiccoding", "blackhansans",
        "dohyeon", "jua", "gaegu", "himelody", "gamjaflower", "gowunbatang", "gowundodum", "hahmlet", "kirangharang", "poorstory", "songmyung",
        "stylish", "cutefont", "dokdo", "eastseadokdo", "blackandwhitepicture", "yeonsung", "sunflower", "gugi", "gothica1", "ibmplexsanskr",
        "dongle", "orbit", "singleday", "diphylleia", "bagelfatone", "grandifloraone", "moiraione", "gasoekone", "nanumbrushscript"]
out = sys.argv[1]; os.makedirs(out, exist_ok=True); ua = {"User-Agent": "font-fetch"}
got = 0
for fam in dict.fromkeys(FAMS):
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/google/fonts/contents/ofl/{fam}", headers=ua)
        items = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as ex: print("없음", fam, ex); continue
    for it in items:
        n = it["name"]
        if not n.lower().endswith((".ttf", ".otf")): continue
        dst = os.path.join(out, n)
        if os.path.exists(dst): continue
        try:
            urllib.request.urlretrieve(it["download_url"], dst); got += 1; time.sleep(0.3)
        except Exception as ex: print("실패", n, ex)
    print("받음", fam, flush=True)
print("새로 받은 파일", got)
