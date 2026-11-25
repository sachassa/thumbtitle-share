# tt_final_assets — 재현 결과 폴더(값/·그림/ 에 여러 편)에서 영상마다 최종 화면용 폴더를 만든다.
#   python -I -X utf8 tt_final_assets.py <재현 폴더> <만들 곳 이름(예: 최종_영상)> <영상id> [<영상id> ...]
#   → <재현 폴더>/<만들 곳>/<영상id>/ 에 값/(결과·검수·눈확인·맞춤) · 그림/(원본·재현·배경·색겹침·제목칸·글자 카드)
#   그다음 tt_newui_html.py 로 그 폴더의 새화면.html 을 만들고, tt_final_html.py 로 묶는다.
# 값은 모두 재현·검수 파일에서 옮긴다(새로 지어 넣지 않음):
#   글꼴·크기·가로/세로 비율·덧굵기·테두리 = 재현 결과(값/<id>.json 의 줄) · 「맞춤 겹침」 = 재현 결과 글자별 iou ·
#   검수 겹침·글자 상자 = 독립 검수(값/<id>_검수.json) · 눈 확인 = 값/눈확인.json
# 운영자 2026-11-25 「다 반영해죠」(최종 화면에 끝낸 11편 모두).
import json, os, sys, shutil
import numpy as np
from PIL import Image


def rj(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d


def build(R0, out, vid):
    D = os.path.join(R0, out, vid); G = os.path.join(D, "그림"); V_ = os.path.join(D, "값")
    os.makedirs(os.path.join(G, "글자"), exist_ok=True); os.makedirs(V_, exist_ok=True)
    for k in ("원본", "재현", "배경"):
        s = os.path.join(R0, "그림", f"{vid}_{k}.png")
        if os.path.exists(s): shutil.copyfile(s, os.path.join(G, f"{vid}_{k}.png"))
    for k in (f"{vid}.json", f"{vid}_검수.json"): shutil.copyfile(os.path.join(R0, "값", k), os.path.join(V_, k))
    eye = (rj(os.path.join(R0, "값", "눈확인.json"), {}) or {}).get(vid)
    json.dump({vid: eye} if eye else {}, open(os.path.join(V_, "눈확인.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    R = rj(os.path.join(R0, "값", f"{vid}.json")); V = rj(os.path.join(R0, "값", f"{vid}_검수.json"))
    o = np.asarray(Image.open(os.path.join(G, f"{vid}_원본.png")).convert("RGB")).astype(int)
    r = np.asarray(Image.open(os.path.join(G, f"{vid}_재현.png")).convert("RGB")).astype(int)
    bp = os.path.join(G, f"{vid}_배경.png")
    bg = np.asarray(Image.open(bp).convert("RGB")).astype(int) if os.path.exists(bp) else o
    mo = np.abs(o - bg).sum(2) > 60; mr = np.abs(r - bg).sum(2) > 60
    col = np.zeros(o.shape, np.uint8); col[mo & mr] = 255; col[mo & ~mr] = (255, 0, 255); col[mr & ~mo] = (0, 200, 0)
    Image.fromarray(col).save(os.path.join(G, f"{vid}_색겹침.png"))
    # 제목 줄 = 독립 검수가 본 줄(제목줄만 견줌 — 글자고르기.json 「제목줄」)
    vlines = {L["text"]: L for L in V["lines"]}
    fit, cards = [], []
    H_, W_ = o.shape[:2]
    allb = [g["o_box"] for L in V["lines"] for g in L["glyphs"] if g.get("o_box")]
    tb = [max(0, int(min(b[0] for b in allb)) - 20), max(0, int(min(b[1] for b in allb)) - 20),
          min(W_, int(max(b[2] for b in allb)) + 20), min(H_, int(max(b[3] for b in allb)) + 20)] if allb else [0, 0, W_, H_]
    for nm, a in (("원본", o), ("재현", r), ("색겹침", col)):
        Image.fromarray(a.astype(np.uint8)).crop(tuple(tb)).save(os.path.join(G, f"제목칸_{nm}.png"))
    li = 0
    for k, L in enumerate(R["lines"]):
        if L["text"] not in vlines: continue
        li += 1; VL = vlines[L["text"]]
        f = L.get("font") or {}; fname = f.get("best") if isinstance(f, dict) else str(f)
        ious = [g["iou"] for g in R.get("glyphs", []) if g.get("line") == k]
        chars = [c for c in L["text"] if not c.isspace()]
        sp = L.get("spans") or []
        colors = []
        for i, c in enumerate(L["text"]):
            s = next((s for s in sp if s["i0"] <= i <= s["i1"]), sp[-1] if sp else {"color": "#000000"})
            colors.append((s.get("grad") or {}).get("start") or s.get("color") or "#000000")
        gl = L.get("glyphs") or []
        hs = sum(g["sx"] for g in gl) / len(gl) if gl else 1.0; vs = sum(g["sy"] for g in gl) / len(gl) if gl else 1.0
        boxes = [dict(i=i, ch=g["ch"], box=[int(v) for v in g["o_box"]]) for i, g in enumerate(VL["glyphs"]) if g.get("o_box")]
        fit.append(dict(text=L["text"], font=fname or "?", line=li, size=round(L.get("size_px", 0), 2), hs=round(hs, 4), vs=round(vs, 4),
                        bold=round(L.get("bold_px", 0) or 0, 3), colors=colors, outline_px=L.get("outline_px") or 0, outline_color=L.get("outline_color") or "",
                        glyphs=[[c, ious[i]] for i, c in enumerate(chars) if i < len(ious)], boxes=boxes))
        for gi, (g, bx) in enumerate(zip(VL["glyphs"], boxes)):
            x0, y0, x1, y1 = bx["box"]; x0 = max(0, x0 - 6); y0 = max(0, y0 - 6); x1 = min(W_, x1 + 6); y1 = min(H_, y1 + 6)
            for nm, a in (("o", o), ("r", r), ("c", col)):
                Image.fromarray(a[y0:y1, x0:x1].astype(np.uint8)).save(os.path.join(G, "글자", f"{li}_{gi}_{nm}.png"))
            cards.append(dict(line=li, i=gi, ch=g["ch"], fit=(ious[gi] if gi < len(ious) else None), f1=g.get("f1"), d_box=g.get("d_box"),
                              vbox_w=round(g["o_box"][2] - g["o_box"][0], 1), box_w=bx["box"][2] - bx["box"][0]))
    json.dump(fit, open(os.path.join(V_, "페이퍼로지_맞춤.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)   # 이름은 화면 프로그램이 읽는 이름 그대로(내용 = 이 영상의 맞춘 값)
    cnt = dict(both=int((mo & mr)[tb[1]:tb[3], tb[0]:tb[2]].sum()), o_only=int((mo & ~mr)[tb[1]:tb[3], tb[0]:tb[2]].sum()), r_only=int((mr & ~mo)[tb[1]:tb[3], tb[0]:tb[2]].sum()))
    json.dump(dict(title_box=tb, pixels=cnt, cards=cards), open(os.path.join(V_, "화면용.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return D, len(fit), len(cards)


if __name__ == "__main__":
    R0, out = sys.argv[1], sys.argv[2]
    for v in sys.argv[3:]:
        print(v, build(R0, out, v), flush=True)
