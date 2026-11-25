# tt_fontnames — 받아 둔 글꼴 파일마다 이름표(name 테이블)의 모든 이름(한글·영문 가족 이름, 전체 이름)을 모은다.
# 산돌구름 후보 이름(대개 한글)을 이 PC 파일과 짝짓는 데 쓴다. 결과: <글꼴 폴더>/_이름.json {경로: [이름...]}
#   python -I tt_fontnames.py <font_pool 폴더>
import json, os, sys
from fontTools.ttLib import TTFont
root = sys.argv[1]; cm = json.load(open(os.path.join(root, "_cmap.json"), encoding="utf-8")); out = {}
for p in cm:
    try:
        f = TTFont(p, lazy=True, fontNumber=0)
        ns = []
        for r in f["name"].names:
            if r.nameID in (1, 2, 4, 6, 16, 17):
                try: s = r.toUnicode().strip()
                except Exception: continue
                if s and s not in ns: ns.append(s)
        out[p] = ns; f.close()
    except Exception as ex: out[p] = []
json.dump(out, open(os.path.join(root, "_이름.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(len(out), "파일 · 이름 없는 파일", sum(1 for v in out.values() if not v), "· 한글 이름 있는 파일", sum(1 for v in out.values() if any("\uac00" <= ch <= "\ud7a3" for n in v for ch in n)))
