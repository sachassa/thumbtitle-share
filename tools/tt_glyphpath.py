# tt_glyphpath — 글꼴 파일에서 글자 윤곽선(SVG path)을 뽑는다. tt_typo3가 Chrome의 정수 픽셀 맞춤(힌팅) 없이 소수 자리까지 그리려고 쓴다.
#   (시스템 파이썬 + fontTools — 이 PC에 이미 있음)  python -I tt_glyphpath.py <요청.json> <결과.json>
#   요청: [{"file": 글꼴 경로, "wght": 굵기 또는 null, "chars": "글자들"}, ...] → 결과: {"<file>|<wght>": {"upm": N, "g": {글자: path d}}}
import json, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen

req = json.load(open(sys.argv[1], encoding="utf-8")); out = {}
for q in req:
    key = f'{q["file"]}|{q.get("wght")}'
    f = TTFont(q["file"], fontNumber=0)
    gs = f.getGlyphSet(location={"wght": q["wght"]}) if q.get("wght") and "fvar" in f else f.getGlyphSet()
    cmap = f.getBestCmap(); g = {}
    for ch in set(q["chars"]):
        name = cmap.get(ord(ch))
        if not name: continue
        pen = SVGPathPen(gs); gs[name].draw(pen); g[ch] = pen.getCommands()
    out[key] = {"upm": f["head"].unitsPerEm, "g": g}
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False)
