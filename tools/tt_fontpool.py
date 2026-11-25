# tt_fontpool — 글꼴 후보를 넓힌다(OP-20261124-027): 눈누(noonnu.cc, 상업용 무료 한글 글꼴 모음)가 jsDelivr에 걸어 둔
# GitHub 저장소 projectnoonnu/* 의 판(목록에 판이 적혀 있으면 그 판, 없으면 마지막 판)에서 글꼴 파일(woff2/woff/ttf/otf)을 받아 <font_pool>/<저장소>/ 에 둔다.
# 같은 파일은 다시 받지 않는다. 목록 = <font_pool>/_목록.json (저장소·판·파일·크기·글꼴 이름).
# 이용 조건: 눈누는 상업용 무료 글꼴만 싣지만 글꼴마다 조건이 다르다 — 여기서는 이 PC 안에서 「원본 글꼴 알아내기·비교」에만 쓰고,
# 우리 썸네일에 실제로 쓸 글꼴은 눈누 글꼴 쪽의 조건을 따로 확인한다.
#   python -X utf8 tt_fontpool.py <저장소 목록 json: ["이름", ...] 또는 [{"repo":..., "ver":...}, ...]> [받을 폴더]
import json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_config as CFG
OUT = sys.argv[2] if len(sys.argv) > 2 else CFG.FONT_POOL
UA = {"User-Agent": "Mozilla/5.0 (font-pool; internal)"}

def get(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r: return r.read()
        except Exception as e:
            if k == tries - 1: print(f"  실패 {url}: {e}", flush=True); return None
            time.sleep(2 + 3 * k)

repos = json.load(open(sys.argv[1], encoding="utf-8"))
os.makedirs(OUT, exist_ok=True)
idx_p = os.path.join(OUT, "_목록.json")
idx = json.load(open(idx_p, encoding="utf-8")) if os.path.exists(idx_p) else []
have = {(x["repo"], x["file"]) for x in idx}
for n, repo in enumerate(repos, 1):
    pin = None
    if isinstance(repo, dict): pin = repo.get("ver"); repo = repo["repo"]
    if pin: ver = pin   # 판 고정(만든 사람 PC와 같은 파일)
    else:
        meta = get(f"https://data.jsdelivr.com/v1/packages/gh/projectnoonnu/{repo}")
        if not meta: continue
        vers = json.loads(meta).get("versions") or []
        ver = vers[0]["version"] if vers else None
    if not ver: print(f"{n}/{len(repos)} {repo}: 판 없음", flush=True); continue
    fl = get(f"https://data.jsdelivr.com/v1/packages/gh/projectnoonnu/{repo}@{ver}?structure=flat")
    if not fl: continue
    files = [f for f in json.loads(fl)["files"] if f["name"].lower().endswith((".woff2", ".woff", ".ttf", ".otf"))]
    # 같은 이름이 woff2·woff 둘 다 있으면 woff2만
    stems = {}
    for f in files:
        st = os.path.splitext(f["name"])[0]
        if st not in stems or f["name"].lower().endswith(".woff2"): stems[st] = f
    got = 0
    for f in stems.values():
        name = f["name"].lstrip("/").replace("/", "__")
        if (repo, name) in have: continue
        d = os.path.join(OUT, repo); os.makedirs(d, exist_ok=True); p = os.path.join(d, name)
        if not os.path.exists(p):
            b = get(f"https://cdn.jsdelivr.net/gh/projectnoonnu/{repo}@{ver}/" + urllib.parse.quote(f["name"].lstrip("/")))
            if not b: continue
            open(p, "wb").write(b); got += 1; time.sleep(0.2)
        idx.append(dict(repo=repo, ver=ver, file=name, size=f["size"], path=p.replace("\\", "/"))); have.add((repo, name))
    json.dump(idx, open(idx_p, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{n}/{len(repos)} {repo}@{ver}: 글꼴 {len(stems)}개 중 새로 {got}개 · 모두 {len(idx)}개", flush=True)
print("끝", flush=True)
