# tt_lc — 검수 결과(값/<id>_검수.json)에서 줄마다 채움색의 「밝기 차」(L*)·「채도 차」(C*)를 따로 뽑아 표로 찍는다.
#   운영자 2026-11-25 「전체적으로 약간 덜 진해, 명암인지 농도인지 잘 모르겠어」(OP-014). 판정에는 안 씀.
#   값 = 재현 − 원본. 밝기 차 < 0 이면 재현이 더 어두움, 채도 차 < 0 이면 재현이 덜 진함.
import json, os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_verify as V

def rows(path):
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for li, L in enumerate(d.get("lines", [])):
        for k, v in L.get("items", {}).items():
            if not k.startswith("채움색"): continue
            o, r = v.get("o"), v.get("r")
            if not (isinstance(o, str) and isinstance(r, str) and o.startswith("#") and r.startswith("#")): continue
            lo, co = V._lc(o); lr, cr = V._lc(r)
            out.append((li + 1, k, o, r, round(lr - lo, 2), round(cr - co, 2)))
    return out

if __name__ == "__main__":
    folder = sys.argv[1]; ids = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    for p in sorted(glob.glob(os.path.join(folder, "값", "*_검수.json"))):
        vid = os.path.basename(p)[:-len("_검수.json")]
        if ids and vid not in ids: continue
        rs = rows(p)
        if not rs: continue
        print(f"## {vid}"); print("| 줄 | 항목 | 원본 | 재현 | 밝기 차(L*) | 채도 차(C*) |"); print("|---|---|---|---|---|---|")
        for r in rs: print("| %d | %s | %s | %s | %+.2f | %+.2f |" % r)
        lb = [r[4] for r in rs]; cb = [r[5] for r in rs]
        print(f"평균: 밝기 {sum(lb)/len(lb):+.2f} · 채도 {sum(cb)/len(cb):+.2f}\n")
