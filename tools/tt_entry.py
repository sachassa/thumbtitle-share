# tt_entry — 입구: 썸네일 그림 하나 또는 유튜브 주소 하나 → 받기 · 글자 읽기 · 글꼴 찾기 · 맞추기 · 비교 화면
#   (INFO-20261125-002 / 운영자 OP-20261125-004 「썸네일 업로드나 유튜브 주소넣으면 작업가능하게」)
# 쓰는 법:
#   python -X utf8 tt_entry.py <유튜브 주소|영상 번호|그림 파일> [--jobs <작업 폴더들 둘 곳>] [--title "제목"]
#   결과 = <jobs>/<날짜시각>_<번호>/  (값/ 그림/ 비교.html · 입구_진행.json)
#   진행은 화면에 단계 이름·걸린 시간으로 찍고, 입구_진행.json 에도 남긴다(편집 화면이 이 파일을 읽어 보여 줌).
# 받는 것: i.ytimg.com 의 공개 썸네일만(로그인·API 키 없음). 쇼츠는 세로 표지 oardefault, 아니면 maxresdefault → sddefault → hqdefault.
# 그림은 받은 그대로(크기·압축 그대로) 쓴다 — 다시 저장·압축하지 않는다.
import os, sys, re, json, time, argparse, subprocess, hashlib, urllib.request, urllib.error, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tt_config as CFG

HERE = os.path.dirname(os.path.abspath(__file__))
PY = [sys.executable, "-I", "-X", "utf8"]
STAGES = ["받기", "글자 읽기·글꼴 찾기·맞추기", "정밀 맞춤", "검수·색 겹침", "화면 만들기"]


class Fail(Exception):
    """사용자에게 그대로 보일 쉬운 말 오류."""


def vid_of(s):
    s = s.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s): return s, None
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})", s)
    if m: return m.group(1), ("쇼츠" if "/shorts/" in s else None)
    return None, None


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (thumb-title-tool)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, r.read()
    except urllib.error.HTTPError as e: return e.code, b""
    except Exception as e: raise Fail(f"인터넷에서 썸네일을 받지 못했습니다({e.__class__.__name__}). 연결을 확인하거나 그림 파일을 직접 올려 주세요.")


def fetch_thumb(vid, kind):
    """가장 큰 공개 썸네일. 쇼츠면 세로 표지 먼저. (그림 바이트, 받은 주소, 형식)"""
    names = (["oardefault"] if kind != "롱폼" else []) + ["maxresdefault", "sddefault", "hqdefault"]
    for n in names:
        u = f"https://i.ytimg.com/vi/{vid}/{n}.jpg"
        code, b = get(u)
        if code == 200 and len(b) > 2000:
            from PIL import Image; import io
            w, h = Image.open(io.BytesIO(b)).size
            if n == "oardefault" and w >= h and kind != "쇼츠": continue   # 세로가 아니면 롱폼 표지로
            return b, u, ("쇼츠" if h > w else "롱폼")
    raise Fail("이 영상의 썸네일이 없습니다(주소가 틀렸거나 비공개·삭제된 영상일 수 있음).")


def title_of(vid):
    code, b = get(f"https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v={vid}", 10)
    try: return json.loads(b.decode("utf-8")).get("title", "") if code == 200 else ""
    except Exception: return ""


class Prog:
    def __init__(self, job):
        self.job = job; self.t0 = time.time(); self.p = os.path.join(job, "입구_진행.json")
        self.d = dict(시작=time.strftime("%Y-%m-%d %H:%M:%S"), 단계=[dict(이름=s, 상태="대기") for s in STAGES], 상태="진행 중", 안내="")
    def save(self): json.dump(self.d, open(self.p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    def stage(self, i, st, note=""):
        s = self.d["단계"][i]; now = round(time.time() - self.t0, 1)
        if st == "진행 중": s["시작초"] = now
        else: s["걸린초"] = round(now - s.get("시작초", now), 1)
        s["상태"] = st; s["메모"] = note; self.d["경과초"] = now; self.save()
        print(f"[{now:7.1f}초] {STAGES[i]} — {st}{(' · ' + note) if note else ''}", flush=True)
    def end(self, st, note): self.d["상태"] = st; self.d["안내"] = note; self.d["경과초"] = round(time.time() - self.t0, 1); self.save(); print(f"== {st}: {note}", flush=True)


def run(cmd, prog, i, log, timeout):
    """하위 단계 실행. 출력은 로그 파일로, 마지막 줄을 진행 메모로."""
    with open(log, "a", encoding="utf-8") as lf:
        p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        t0 = time.time(); last = ""
        for line in p.stdout:
            lf.write(line); lf.flush(); line = line.strip()
            if line: last = line[:160]; prog.d["단계"][i]["메모"] = last; prog.d["경과초"] = round(time.time() - prog.t0, 1); prog.save()
            if time.time() - t0 > timeout: p.kill(); raise Fail(f"「{STAGES[i]}」이 {timeout}초를 넘어 멈췄습니다.")
        p.wait()
    return p.returncode, last


def write_ai_wait(jobs):
    """끝났지만 AI가 아직 눈으로 안 본 작업 목록 → <jobs>/_AI_확인대기.json (AI 일하는 법 CLAUDE.md 가 이 파일을 보라고 함)."""
    out = []
    for d in sorted(os.listdir(jobs), reverse=True):
        try: j = json.load(open(os.path.join(jobs, d, "입구_진행.json"), encoding="utf-8"))
        except Exception: continue
        if j.get("상태") != "끝": continue
        try: eye = json.load(open(os.path.join(jobs, d, "값", "눈확인.json"), encoding="utf-8"))
        except Exception: eye = {}
        if not eye.get(j.get("영상")):
            out.append(dict(폴더=os.path.join(jobs, d), 영상=j.get("영상"), 제목=j.get("제목"), 끝난때=j.get("시작"),
                            할일=f'원본·재현을 원래 크기로 보고: python tools/tt_status.py eye "{os.path.join(jobs, d)}" {j.get("영상")} "본 것"'))
    json.dump(out, open(os.path.join(jobs, "_AI_확인대기.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description="썸네일 그림 또는 유튜브 주소 하나로 재현 돌리기")
    ap.add_argument("src"); ap.add_argument("--jobs", default=CFG.JOBS)
    ap.add_argument("--title", default=""); ap.add_argument("--job")
    a = ap.parse_args()
    vid, kind = vid_of(a.src)
    isfile = os.path.isfile(a.src)
    if not vid and not isfile:
        print("== 실패: 유튜브 주소(watch?v= · youtu.be/ · shorts/)나 영상 번호 11자, 또는 그림 파일 경로를 넣어 주세요.", flush=True); sys.exit(2)
    if isfile:   # 올린 그림: 내용으로 번호를 만듦(11자, 같은 그림이면 같은 번호)
        raw = open(a.src, "rb").read(); vid = "up" + hashlib.sha1(raw).hexdigest()[:9]
    job = a.job or os.path.join(a.jobs, time.strftime("%Y%m%d_%H%M%S") + "_" + vid)
    for d in ("thumbs", "값", "그림", "재현"): os.makedirs(os.path.join(job, d), exist_ok=True)
    prog = Prog(job); prog.save(); log = os.path.join(job, "돌림.log")
    print(f"작업 폴더: {job}", flush=True)
    try:
        prog.stage(0, "진행 중")
        if isfile:
            from PIL import Image
            try: im = Image.open(a.src); im.verify(); im = Image.open(a.src); w, h = im.size; fmt = im.format
            except Exception: raise Fail("그림 파일을 열지 못했습니다(jpg·png·webp 그림인지 확인해 주세요).")
            if fmt not in ("JPEG", "PNG", "WEBP"): raise Fail(f"{fmt} 그림은 받지 않습니다(jpg·png·webp만).")
            if fmt == "WEBP":   # 재현 프로그램이 읽는 형식으로 — 화소 그대로 PNG(무손실)로만 바꿈
                im.convert("RGB").save(os.path.join(job, "thumbs", vid + ".jpg"), "PNG")
            else: shutil.copyfile(a.src, os.path.join(job, "thumbs", vid + ".jpg"))   # 받은 그대로(확장자만 맞춤, 내용은 원래 형식)
            title = a.title or os.path.splitext(os.path.basename(a.src))[0]; kind = "쇼츠" if h > w else "롱폼"; got = os.path.basename(a.src)
        else:
            b, got, kind = fetch_thumb(vid, kind)
            open(os.path.join(job, "thumbs", vid + ".jpg"), "wb").write(b)
            title = a.title or title_of(vid) or vid
        json.dump({"vids": [dict(id=vid, t=title, g="", d="")]}, open(os.path.join(job, "영상목록.json"), "w", encoding="utf-8"), ensure_ascii=False)
        open(os.path.join(job, "ids.tsv"), "w", encoding="utf-8").write(f"video_id\t형식\n{vid}\t{kind}\n")
        prog.d.update(영상=vid, 제목=title, 형식=kind, 받은곳=got); prog.stage(0, "끝", f"{kind} · {got}")

        prog.stage(1, "진행 중")
        rc, last = run(PY + ["tt_typo3.py", "--ids", os.path.join(job, "ids.tsv"), "--img-dir", os.path.join(job, "thumbs"), "--out", job,
                             "--list", os.path.join(job, "영상목록.json"), "--only", vid], prog, 1, log, 1800)
        if not os.path.exists(os.path.join(job, "값", vid + ".json")):
            txt = open(log, encoding="utf-8", errors="replace").read()
            if "글자 없음" in txt or "줄 없음" in txt or "제목 줄" in txt and "0개" in txt: raise Fail("썸네일에서 제목 글자를 찾지 못했습니다(글자가 없거나 너무 작음).")
            raise Fail(f"재현이 끝나지 못했습니다 — 마지막 기록: {last}")
        R = json.load(open(os.path.join(job, "값", vid + ".json"), encoding="utf-8"))
        if not R.get("lines"): raise Fail("썸네일에서 제목 글자를 찾지 못했습니다(글자가 없거나 너무 작음).")
        nofont = [l.get("text", "") for l in R["lines"] if not l.get("font")]
        prog.stage(1, "끝", f"줄 {len(R['lines'])}개" + (f" · 글꼴 못 찾은 줄: {', '.join(nofont)}" if nofont else ""))

        prog.stage(2, "진행 중"); rc, last = run(PY + ["tt_refine.py", job, vid], prog, 2, log, 1200); prog.stage(2, "끝" if rc == 0 else "건너뜀", last)
        prog.stage(3, "진행 중")
        run(PY + ["tt_verify.py", job, "--only", vid], prog, 3, log, 900); run(PY + ["tt_color_overlay.py", job, "--only", vid], prog, 3, log, 300)
        V = {}
        try: V = json.load(open(os.path.join(job, "값", vid + "_검수.json"), encoding="utf-8"))
        except Exception: pass
        prog.stage(3, "끝", "100% 일치" if V.get("all_ok") else "일치 안 됨")
        prog.stage(4, "진행 중")
        rc, last = run(PY + ["tt_compare_html3.py", job, "--name", "비교.html"], prog, 4, log, 300)
        if rc != 0 or not os.path.exists(os.path.join(job, "비교.html")): raise Fail(f"비교 화면을 만들지 못했습니다 — {last}")   # 오류를 「끝」으로 적던 것 고침(2026-11-25, 실측)
        prog.stage(4, "끝", "비교.html")
        prog.end("끝", ("100% 일치" if V.get("all_ok") else "일치 안 됨") + " — 비교 화면: " + os.path.join(job, "비교.html")
                 + (f" · 글꼴 못 찾은 줄: {', '.join(nofont)}" if nofont else ""))
        write_ai_wait(os.path.dirname(job))
    except Fail as e:
        for i, s in enumerate(prog.d["단계"]):
            if s["상태"] == "진행 중": prog.stage(i, "실패", str(e))
        prog.end("실패", str(e)); sys.exit(1)
    except Exception as e:
        import traceback; traceback.print_exc()
        prog.end("실패", f"예상 못 한 오류: {e}"); sys.exit(1)


if __name__ == "__main__":
    main()
