# tt_editor — 재현 결과를 운영자가 직접 고쳐 보는 편집 화면(이 PC 안에서만, 127.0.0.1)
# 운영자 2026-11-25: 「편집 마다 기능이 있는데 … 마우스로 끌어당기면 옆으로 늘어나기도 하고 위로도」 ·
#   「그림자넣기 음영 등 다른 사용툴 기능을 가져와서 적용하고 테스트 해봐」 · 「나도 쓸수있게 우리 html에도 기능 추가해죠」
# 쓰는 법: python tt_editor.py <재현 폴더(값·그림 있는 곳)> [--port 8765]  → 브라우저에서 http://127.0.0.1:8765/
# 보내는 것: 화면(tt_editor.html), 결과 값(값/<id>.json), 원본·배경 그림(그림/<id>_원본.png·_배경.png), 글꼴 파일(우리 글꼴 목록에 있는 것만).
# 받는 것: 편집한 값 → 값/<id>_편집.json (재현 결과 파일은 건드리지 않음).
# 입구(INFO-20261125-002): POST /entry (그림 바이트 또는 {"url":…}) → tt_entry.py 를 돌려 <jobs>/<작업>/ 에 재현, GET /job/<작업> = 진행.
#   작업 폴더 결과는 ?r=<작업> 을 붙여 같은 화면으로 봄. 인터넷으로 나가는 것은 tt_entry 가 공개 썸네일(i.ytimg.com)·제목(oembed)을 받을 때뿐.
import os, sys, json, argparse, mimetypes, urllib.parse, subprocess, re, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
_FONTS = None
def fonts():
    """글꼴 파일 이름 → 경로(우리 글꼴 목록에 든 것만 보냄 — 아무 파일이나 읽히지 않게)."""
    global _FONTS
    if _FONTS is None:
        import tt_fontid as FID
        _FONTS = {}
        for c in FID.pool_fonts():
            _FONTS.setdefault(os.path.basename(c[1]), c[1])
        for c in FID.prefer_list():
            _FONTS.setdefault(os.path.basename(c[1]), c[1])
    return _FONTS

_FN = None
def fonts_by_name():
    """글꼴 이름 → 경로(결과 파일에 글꼴이 이름으로만 적힌 경우 — 롱폼 결과 등)."""
    global _FN
    if _FN is None:
        import tt_fontid as FID
        _FN = {}
        for c in list(FID.pool_fonts()) + list(FID.prefer_list()): _FN.setdefault(c[0], c[1])
    return _FN

def titles(root):
    """영상 번호 → 제목. 결과 폴더 옆 영상목록.json, 입구 작업 폴더면 그 안의 영상목록.json·입구_진행.json(2026-11-25 외부 설치 시험: 작업 폴더로 켜면 제목이 빈칸 — 실측)."""
    out = {}
    for p in (os.path.join(os.path.dirname(root.rstrip("/\\")), "영상목록.json"), os.path.join(root, "영상목록.json")):
        try:
            L = json.load(open(p, encoding="utf-8")); L = L if isinstance(L, list) else (L.get("vids") or L.get("videos") or [])
            for x in L:
                k = x.get("id") or x.get("video_id"); t = x.get("t") or x.get("title") or ""
                if k and t: out[k] = t
        except Exception:
            pass
    try:
        j = json.load(open(os.path.join(root, "입구_진행.json"), encoding="utf-8"))
        if j.get("영상") and j.get("제목"): out.setdefault(j["영상"], j["제목"])
    except Exception:
        pass
    return out

def ai_wait(jobs):
    """입구 작업 중 「끝」인데 눈 확인 기록(값/눈확인.json 에 그 영상)이 없는 것."""
    out = []
    for d in sorted(os.listdir(jobs), reverse=True) if os.path.isdir(jobs) else []:
        pj = os.path.join(jobs, d, "입구_진행.json")
        try: j = json.load(open(pj, encoding="utf-8"))
        except Exception: continue
        if j.get("상태") != "끝": continue
        try: eye = json.load(open(os.path.join(jobs, d, "값", "눈확인.json"), encoding="utf-8"))
        except Exception: eye = {}
        if not eye.get(j.get("영상")): out.append(dict(job=d, 폴더=os.path.join(jobs, d), 영상=j.get("영상"), 제목=j.get("제목")))
    return out

class H(BaseHTTPRequestHandler):
    root = "."; jobs = "."
    def R(self, q):   # ?r=<작업> 이면 그 작업 폴더, 아니면 처음 폴더
        r = os.path.basename((q.get("r") or [""])[0])
        return os.path.join(self.jobs, r) if r and os.path.isdir(os.path.join(self.jobs, r)) else self.root
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
    def _file(self, p):
        if not os.path.isfile(p): return self._send(404, '{"오류":"파일 없음"}')
        ct = mimetypes.guess_type(p)[0] or "application/octet-stream"
        if p.endswith(".woff2"): ct = "font/woff2"
        self._send(200, open(p, "rb").read(), ct)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); path = urllib.parse.unquote(u.path)
        root = self.R(q); V = os.path.join(root, "값"); G = os.path.join(root, "그림")
        if path in ("/", "/index.html"): return self._file(os.path.join(HERE, "tt_editor.html"))
        if path == "/list":
            T = titles(root); out = []
            for b in (sorted(os.listdir(V)) if os.path.isdir(V) else []):
                if b.endswith(".json") and not b.startswith("_") and "_" not in b.replace(".json", "")[11:] and len(b) == 16:
                    vid = b[:-5]
                    if os.path.exists(os.path.join(G, f"{vid}_원본.png")): out.append(dict(id=vid, title=T.get(vid, "")))
            return self._send(200, json.dumps(out, ensure_ascii=False))
        if path.startswith("/data/"):
            vid = os.path.basename(path[6:])
            d = json.load(open(os.path.join(V, f"{vid}.json"), encoding="utf-8"))
            ed = os.path.join(V, f"{vid}_편집.json")
            res = dict(id=vid, canvas=d.get("canvas"), lines=d["lines"], edit=json.load(open(ed, encoding="utf-8")) if os.path.exists(ed) else None)
            return self._send(200, json.dumps(res, ensure_ascii=False))
        if path.startswith("/img/"):
            vid, kind = path[5:].split("/", 1)
            if kind not in ("원본", "배경", "재현"): return self._send(404, "{}")
            return self._file(os.path.join(G, f"{os.path.basename(vid)}_{kind}.png"))
        if path == "/font":
            f = fonts().get(os.path.basename(q.get("f", [""])[0])) or fonts_by_name().get((q.get("n") or [""])[0])
            return self._file(f) if f else self._send(404, '{"오류":"글꼴 목록에 없음"}')
        if path == "/jobs":   # 입구로 돌린 작업들(새것 먼저)
            out = []
            for d in sorted(os.listdir(self.jobs), reverse=True) if os.path.isdir(self.jobs) else []:
                pj = os.path.join(self.jobs, d, "입구_진행.json")
                if os.path.exists(pj):
                    try: j = json.load(open(pj, encoding="utf-8"))
                    except Exception: continue
                    out.append(dict(job=d, 제목=j.get("제목", ""), 상태=j.get("상태"), 경과초=j.get("경과초"), 영상=j.get("영상")))
            return self._send(200, json.dumps(out, ensure_ascii=False))
        if path.startswith("/job/"):
            pj = os.path.join(self.jobs, os.path.basename(path[5:]), "입구_진행.json")
            return self._file(pj) if os.path.exists(pj) else self._send(404, '{"오류":"그런 작업 없음"}')
        if path.startswith("/view/"):   # 작업 폴더의 비교 화면·그림(그 폴더 안 파일만)
            rel = path[6:].split("/", 1); job = os.path.join(self.jobs, os.path.basename(rel[0]))
            f = os.path.normpath(os.path.join(job, rel[1] if len(rel) > 1 else "비교.html"))
            if not f.startswith(os.path.normpath(job)): return self._send(403, "{}")
            return self._file(f)
        if path == "/fontlist":
            return self._send(200, json.dumps(sorted(fonts().keys()), ensure_ascii=False))
        if path == "/ai_wait":   # 끝났지만 AI 눈 확인을 아직 안 한 작업
            return self._send(200, json.dumps(ai_wait(self.jobs), ensure_ascii=False))
        # 그 밖: 처음 폴더 안의 파일(메인 화면 최종.html · 영상별 화면 · 그림) — 폴더 밖으로는 못 나감
        f = os.path.normpath(os.path.join(self.root, path.lstrip("/")))
        if f.startswith(os.path.normpath(self.root) + os.sep) and os.path.isfile(f): return self._file(f)
        self._send(404, "{}")
    def do_POST(self):
        u = urllib.parse.urlparse(self.path); path = urllib.parse.unquote(u.path); q = urllib.parse.parse_qs(u.query)
        if path == "/entry":   # 입구: 그림 바이트(Content-Type image/*) 또는 {"url": "..."}
            n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n); ct = self.headers.get("Content-Type") or ""
            os.makedirs(self.jobs, exist_ok=True)
            if ct.startswith("image/"):
                if n > 30 * 1024 * 1024: return self._send(400, json.dumps({"오류": "그림이 너무 큽니다(30MB까지)"}, ensure_ascii=False))
                name = re.sub(r"[^\w.가-힣-]", "_", urllib.parse.unquote(self.headers.get("X-Name") or "그림.jpg"))[:60]
                up = os.path.join(self.jobs, "_올린그림"); os.makedirs(up, exist_ok=True); src = os.path.join(up, f"{time.strftime('%H%M%S')}_{name}")
                open(src, "wb").write(body)
            else:
                try: src = json.loads(body.decode("utf-8"))["url"].strip()
                except Exception: return self._send(400, json.dumps({"오류": "주소를 못 읽음"}, ensure_ascii=False))
            job = time.strftime("%Y%m%d_%H%M%S") + "_" + re.sub(r"[^A-Za-z0-9_-]", "", os.path.basename(src))[-11:]
            jp = os.path.join(self.jobs, job); os.makedirs(jp, exist_ok=True)
            subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(HERE, "tt_entry.py"), src, "--job", jp],
                             cwd=HERE, stdout=open(os.path.join(jp, "입구.log"), "w", encoding="utf-8"), stderr=subprocess.STDOUT)
            return self._send(200, json.dumps({"job": job}, ensure_ascii=False))
        if not path.startswith("/save/"): return self._send(404, "{}")
        vid = os.path.basename(path[6:]); n = int(self.headers.get("Content-Length") or 0)
        try:
            d = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._send(400, json.dumps({"오류": f"값을 못 읽음: {e}"}, ensure_ascii=False))
        p = os.path.join(self.R(q), "값", f"{vid}_편집.json")
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        self._send(200, json.dumps({"저장": p}, ensure_ascii=False))

if __name__ == "__main__":
    import tt_config as CFG
    ap = argparse.ArgumentParser(); ap.add_argument("root", nargs="?", help="재현 결과 폴더(값·그림 있는 곳). 비우면 입구 작업 폴더만 봄"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--jobs", help="입구 작업 폴더들을 둘 곳(기본: tt_config.JOBS)"); a = ap.parse_args()
    H.jobs = a.jobs or CFG.JOBS; os.makedirs(H.jobs, exist_ok=True); H.root = a.root or H.jobs
    s = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"편집 화면: http://127.0.0.1:{a.port}/  (끄려면 Ctrl+C)", flush=True)
    s.serve_forever()
