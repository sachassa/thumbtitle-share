// tt_watchdog — 재현 작업 감시(운영자 2026-11-24 「지시 후에 모니터링하고 실측으로 확인해 · 기계 오류면 예외·타임아웃 등으로 인지 가능하게」).
//   node tools/tt_watchdog.mjs <로그 파일> <진행 파일 값/_진행.json> [--stall 300] [--timeout 1320] [--every 15]
// 한 줄 = 한 알림(Monitor 로 띄운다). 알리는 것:
//   ▶ 시작 · ■ 결과(완료/미완료) · ▷ 단계(글꼴 알아내기·정답 줄·다시 볼 글자 등)
//   ⚠오류 (Traceback·오류·Error·Killed·MemoryError)
//   ⚠멈춤  (진행 파일이 --stall 초 동안 안 바뀜 — 걸려 있거나 아주 느림)
//   ⚠시간초과 (한 영상이 --timeout 초 넘음)
//   ⚠죽음  (진행 파일의 프로세스가 없어졌는데 「끝/오류」 표시가 없음 — 강제 종료·튕김)
// 기본값 근거: 멈춤 300초 = 실측에서 단계 사이 가장 긴 빈 시간(글꼴 한 줄 139초)의 약 2배 / 시간초과 1320초 = 실측 가장 긴 영상 11분의 2배. (근거: 2026-11-24 기록)
import fs from "node:fs";
import { execSync } from "node:child_process";
// 멈춤처럼 보일 때 그 프로세스가 CPU를 쓰는지 3초 재서 「느림(일하는 중)」과 「진짜 멈춤」을 가른다(2026-11-24 실측: 전체 비교 한 단계가 300초 넘게 로그 없이 CPU 98%로 돎).
function cpuBusy(pid) {
  try {
    const out = execSync(`powershell -NoProfile -Command "$p=Get-Process -Id ${pid} -EA Stop; $a=$p.CPU; Start-Sleep 3; $p.Refresh(); [math]::Round(($p.CPU-$a)/3*100)"`, { encoding: "utf8", timeout: 20000 }).trim();
    return Number(out);
  } catch { return null; }
}

const [logF, stF] = process.argv.slice(2);
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? Number(process.argv[i + 1]) : d; };
const STALL = opt("--stall", 300), TIMEOUT = opt("--timeout", 1320), EVERY = opt("--every", 15) * 1000;
const say = (s) => console.log(`${new Date().toTimeString().slice(0, 8)} ${s}`);
let pos = fs.existsSync(logF) ? fs.statSync(logF).size : 0;
let lastStage = "", warned = {}, sawResult = false, endTicks = 0;
// 스스로 끝나기(2026-11-25 외부 설치 시험: 작업이 끝나도 감시가 안 끝나 손으로 꺼야 했음 — 실측):
//   입구_진행.json(로그 옆 또는 진행 파일 두 칸 위)의 상태가 「끝」·「실패」이거나, ■ 결과를 알린 뒤 진행 파일의 프로세스가 사라지면 한 번 더 읽고 끝냄.
import path from "node:path";
const entryF = [path.join(path.dirname(logF), "입구_진행.json"), path.join(path.dirname(path.dirname(stF)), "입구_진행.json")].find((f) => fs.existsSync(f)) || path.join(path.dirname(logF), "입구_진행.json");
function finished() {
  try { const e = JSON.parse(fs.readFileSync(entryF, "utf8")); if (e.상태 === "끝" || e.상태 === "실패") return `입구 작업 ${e.상태}${e.안내 ? " — " + String(e.안내).slice(0, 120) : ""}`; } catch {}
  try { const st = JSON.parse(fs.readFileSync(stF, "utf8")); if (sawResult && st.pid && !alive(st.pid)) return "결과를 낸 뒤 프로세스가 끝남"; } catch {}
  return null;
}
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === "EPERM"; } };

function tick() {
  // 1) 로그 새 줄
  try {
    const size = fs.statSync(logF).size;
    if (size > pos) {
      const fd = fs.openSync(logF, "r"); const buf = Buffer.alloc(size - pos); fs.readSync(fd, buf, 0, buf.length, pos); fs.closeSync(fd); pos = size;
      for (const l of buf.toString("utf8").split(/\r?\n/)) {
        if (/^==/.test(l)) say("▶ " + l.replace(/^==\s*/, ""));
        else if (/: (통과|못 통과) ·/.test(l)) { sawResult = true; say("■ 결과 " + l.slice(0, 140)); }
        else if (/Traceback|: 오류 —|Error|Killed|MemoryError|실패/.test(l) && !/RuntimeWarning/.test(l)) say("⚠오류 " + l.slice(0, 160));
        else if (/글꼴 알아내기|다시 볼 글자|Claude 정답 줄로 고침|묶음 미리 계산|전체 비교 건너뜀/.test(l)) say("▷ " + l.trim().slice(0, 150));
      }
    }
  } catch {}
  // 2) 진행 파일: 멈춤·시간초과·죽음
  try {
    const st = JSON.parse(fs.readFileSync(stF, "utf8"));
    const idle = Date.now() / 1000 - st.at;
    const key = `${st.vid}|${st.stage}`;
    if (st.done) { lastStage = key; return; }
    if (st.pid && !alive(st.pid) && !warned["dead" + key]) { warned["dead" + key] = 1; say(`⚠죽음 ${st.vid}: 프로세스(${st.pid})가 없어졌는데 끝/오류 표시가 없음 — 마지막 단계 「${st.stage.slice(0, 80)}」`); }
    if (idle > STALL && !warned["stall" + key]) { warned["stall" + key] = 1; const cpu = cpuBusy(st.pid);
      if (cpu !== null && cpu >= 20) say(`… 느림(멈춤 아님) ${st.vid}: ${Math.round(idle)}초째 새 단계 없음, 프로세스는 CPU ${cpu}%로 일하는 중 — 단계 「${st.stage.slice(0, 60)}」(시작 뒤 ${st.secs}초)`);
      else say(`⚠멈춤 ${st.vid}: ${Math.round(idle)}초째 진행 없음 · CPU ${cpu === null ? "못 잼" : cpu + "%"} — 걸려 있을 수 있음 · 마지막 단계 「${st.stage.slice(0, 60)}」(시작 뒤 ${st.secs}초)`);
      setTimeout(() => { delete warned["stall" + key]; }, STALL * 1000); }
    const total = st.secs + idle;
    if (total > TIMEOUT && !warned["to" + st.vid]) { warned["to" + st.vid] = 1; say(`⚠시간초과 ${st.vid}: ${Math.round(total)}초 넘음(기준 ${TIMEOUT}초)`); }
  } catch {}
}
say(`감시 시작 — 멈춤 ${STALL}초 · 시간초과 ${TIMEOUT}초 · ${EVERY / 1000}초마다`);
const timer = setInterval(() => {
  tick();
  const why = finished();
  if (why && ++endTicks >= 2) { tick(); say(`□ 감시 끝 — ${why}`); clearInterval(timer); process.exit(0); }   // 두 번 연달아 끝으로 보일 때(마지막 로그 줄까지 읽고)
}, EVERY); tick();
