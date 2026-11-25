# tt_status — 영상마다 「할 일을 다 했나」 상태(운영자 2026-11-24 「100%가 안 되는 건 완료야 · 할 걸 다 안 한 건 미완료니까 안 보여도 돼 · 대신 진행 중·완료 안 됨 리스트로 보여줘」).
#   완료   = 할 일을 모두 함: ①재현 끝 ②독립 검수(재현 뒤에 함) ③색 겹침 그림 ④Claude가 원래 크기로 직접 봄(재현 뒤에 함)
#            결과는 따로: 「100% 일치」 또는 「일치 안 됨(검수 N개 중 M개 다름)」 — 완료여도 일치가 아닐 수 있다.
#   진행 중 = 값/_진행.json 이 이 영상을 돌리는 중
#   대기    = 값/_대기열.json 에 올라 있고 아직 그 뒤로 재현이 안 끝남
#   완료 안 됨 = 위 ①~④ 중 빠진 것이 있음(빠진 것을 사유로 적음)
#   Claude 눈 확인 기록: python tt_status.py eye <결과 폴더> <id> "본 것"  → 값/눈확인.json 에 {at, note}
import json, os, sys, time

def _rj(p, d=None):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return d

def pid_alive(pid):
    if not pid: return False
    if os.name == "nt":
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h: return False
        code = ctypes.c_ulong(); ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code)); ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259
    try: os.kill(int(pid), 0); return True
    except OSError: return False

def status(out, vid):
    """돌려줌: dict(state=완료|진행 중|대기|완료 안 됨, match=None|True|False, why=[...], vr=검수값|None)"""
    V = os.path.join(out, "값")
    pj = os.path.join(V, f"{vid}.json")
    run_t = os.path.getmtime(pj) if os.path.exists(pj) else None
    st = _rj(os.path.join(V, "_진행.json"), {}) or {}
    if st.get("vid") == vid and not st.get("done") and pid_alive(st.get("pid")):
        return dict(state="진행 중", match=None, why=[f'{st.get("stage", "")[:60]} (시작 뒤 {st.get("secs", 0):.0f}초)'], vr=None)
    q = (_rj(os.path.join(V, "_대기열.json"), {}) or {}).get(vid)
    if q and (run_t is None or run_t < q["at"]):
        return dict(state="대기", match=None, why=[q.get("why", "")], vr=None)
    why = []
    if run_t is None:
        return dict(state="완료 안 됨", match=None, why=["재현 안 함"], vr=None)
    if st.get("vid") == vid and st.get("done") == "오류": why.append("재현 중 오류로 멈춤")
    vp = os.path.join(V, f"{vid}_검수.json"); vr = _rj(vp)
    if vr is None: why.append("독립 검수 안 함")
    elif os.path.getmtime(vp) < run_t: why.append("독립 검수가 옛 재현 것(다시 검수해야)"); vr = None
    cp = os.path.join(out, "그림", f"{vid}_색겹침.png")
    if not os.path.exists(cp) or os.path.getmtime(cp) < run_t: why.append("색 겹침 그림 없음/옛것")
    eye = (_rj(os.path.join(V, "눈확인.json"), {}) or {}).get(vid)
    if not isinstance(eye, dict) or eye.get("at", 0) < run_t: why.append("Claude 눈 확인 안 함(새 결과)")
    if why: return dict(state="완료 안 됨", match=None, why=why, vr=vr)
    return dict(state="완료", match=bool(vr.get("all_ok")), why=[], vr=vr, eye=eye.get("note", ""))

def all_vids(out, meta_ids=()):
    V = os.path.join(out, "값"); ids = set(meta_ids)
    for b in os.listdir(V):
        if b.endswith(".json") and not b.startswith("_") and b not in ("눈확인.json", "글자고르기.json") and not b.endswith(("_실측.json", "_검수.json", "_정밀.json")):
            ids.add(b[:-5])
    ids |= set((_rj(os.path.join(V, "_대기열.json"), {}) or {}).keys())
    return sorted(ids)

def list_html(out, title_of, esc):
    """완료가 아닌 영상 목록(진행 중·대기·완료 안 됨) 표."""
    rows = []
    order = {"진행 중": 0, "대기": 1, "완료 안 됨": 2}
    items = [(v, status(out, v)) for v in all_vids(out)]
    items = [x for x in items if x[1]["state"] != "완료"]
    items.sort(key=lambda x: order[x[1]["state"]])
    for v, s in items:
        rows.append(f'<tr><td>{esc(title_of(v))}</td><td class="st{order[s["state"]]}">{s["state"]}</td><td>{esc(" · ".join(w for w in s["why"] if w))}</td></tr>')
    if not rows: return ""
    return ('<section style="background:#fff;padding:8px 12px;margin:12px"><h3 style="margin:4px 0">진행 중 · 대기 · 완료 안 됨 (결과 그림은 할 일을 다 마친 뒤 나옴)</h3>'
            '<table border="1" cellpadding="4" style="border-collapse:collapse"><tr><th>영상 제목</th><th>상태</th><th>무엇이 남았나</th></tr>'
            + "".join(rows) + '</table><style>.st0{color:#1d4ed8;font-weight:bold}.st1{color:#666}.st2{color:#b45309;font-weight:bold}</style></section>')

if __name__ == "__main__":
    if sys.argv[1] == "eye":
        out, vid, note = sys.argv[2], sys.argv[3], sys.argv[4]
        p = os.path.join(out, "값", "눈확인.json"); d = _rj(p, {}) or {}
        d[vid] = {"at": time.time(), "note": note}
        tmp = p + ".tmp"; json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1); os.replace(tmp, p)
        print("눈 확인 기록:", vid)
        # 입구 작업처럼 비교.html 이 이미 있는 폴더면 바로 다시 만듦(눈 확인 전에는 결과를 숨기므로) — 2026-11-25 외부 설치 시험에서 눈 확인 뒤에도 비교 화면이 비어 있었음(실측)
        if os.path.exists(os.path.join(out, "비교.html")):
            import subprocess
            r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tt_compare_html3.py"), out, "--name", "비교.html"])
            print("비교 화면 다시 만듦" if r.returncode == 0 else f"비교 화면 다시 만들기 실패(rc={r.returncode})")
        # 입구의 「AI 확인 대기」 목록에서도 뺌
        if os.path.exists(os.path.join(out, "입구_진행.json")):
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import tt_entry; tt_entry.write_ai_wait(os.path.dirname(os.path.abspath(out)))
            except Exception as e: print("AI 확인 대기 목록 갱신 못 함:", e)
    elif sys.argv[1] == "queue":   # python tt_status.py queue <결과 폴더> "사유" id id ...
        out, why, ids = sys.argv[2], sys.argv[3], sys.argv[4:]
        p = os.path.join(out, "값", "_대기열.json"); d = _rj(p, {}) or {}
        for v in ids: d[v] = {"at": time.time(), "why": why}
        json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1); print("대기열:", len(ids))
    else:
        out = sys.argv[1]
        for v in all_vids(out):
            s = status(out, v); print(v, s["state"], "" if s["match"] is None else ("100% 일치" if s["match"] else "일치 안 됨"), " · ".join(s["why"]))
