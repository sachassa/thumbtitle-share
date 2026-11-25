# tt_fontcmap — 글꼴 파일마다 이름(가족·굵기)과 들어 있는 글자(U+0000~U+FFFF 비트표)를 적는다. 시스템 파이썬 + fontTools.
#   python -I tt_fontcmap.py <글꼴 경로 목록 txt> <결과 json>   (이미 적힌 파일은 건너뜀)
import base64, json, os, sys
from fontTools.ttLib import TTFont
paths = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
out_p = sys.argv[2]
out = json.load(open(out_p, encoding="utf-8")) if os.path.exists(out_p) else {}
for i, p in enumerate(paths, 1):
    if p in out: continue
    try:
        f = TTFont(p, fontNumber=0, lazy=True)
        nm = f["name"]
        def get(i_):
            for rec in nm.names:
                if rec.nameID == i_ and rec.platformID == 3 and rec.langID == 0x412:
                    try: return rec.toUnicode()
                    except Exception: pass
            r = nm.getDebugName(i_); return r
        bits = bytearray(8192)
        for cp in f.getBestCmap() or {}:
            if cp < 65536: bits[cp >> 3] |= 1 << (cp & 7)
        out[p] = dict(family=get(16) or get(1), style=get(17) or get(2), ko=get(1), vf="fvar" in f,
                      wght=[a.minValue for a in f["fvar"].axes if a.axisTag == "wght"] + [a.maxValue for a in f["fvar"].axes if a.axisTag == "wght"] if "fvar" in f else None,
                      cov=base64.b64encode(bytes(bits)).decode())
    except Exception as e:
        out[p] = dict(error=str(e)[:200])
    if i % 100 == 0: json.dump(out, open(out_p, "w", encoding="utf-8"), ensure_ascii=False); print(i, flush=True)
json.dump(out, open(out_p, "w", encoding="utf-8"), ensure_ascii=False)
print("끝", len(out))
