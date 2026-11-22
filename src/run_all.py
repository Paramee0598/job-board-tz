"""run_all.py — ตัวคุมลำดับ: (budget guard) → fetch → normalize (merge) → build → log

ROOT = Path(__file__).resolve().parent.parent  ← ย้ายโฟลเดอร์ทั้งก้อนได้โดยแก้ที่เดียว
ไม่มี path absolute ใด ๆ ในไฟล์นี้

ใช้:
    python src\\run_all.py                 # รันเต็มตาม config\\switches.json (active preset)
    python src\\run_all.py --skip-fetch     # ใช้ผลดิบที่มีอยู่แล้วใน data\\raw\\<วันนี้>\\
    python src\\run_all.py --preset wide     # เลือก preset ชั้น B
    python src\\run_all.py --clear-session   # ลบ cookie/session แล้วจบ (T0 = ไม่มีอะไรต้องลบ)
    python src\\run_all.py --clear-session --run  # ล้างแล้วรัน pipeline ต่อ
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
DIST = ROOT / "dist"
RUNS = ROOT / "runs"

import fetch_jobspy  # noqa: E402  (อยู่ src\ เดียวกัน)
import fetch_jobthai  # noqa: E402  (jobthai.com ผ่านหน้าเว็บ — ฟรี ไม่ต้องมี token)
import fetch_jobtopgun  # noqa: E402  (jobtopgun.com ผ่านหน้าเว็บ — ฟรี ไม่ต้องมี token)
import normalize as norm  # noqa: E402

BUDGET_CAP_USD = 4.0
PAID_BOARDS = ("jobthai", "jobtopgun", "facebook")

# เว็บที่ HTML มาฝั่ง server (ฟรี): (ชื่อแหล่ง, โมดูล, สวิตช์ใน config\switches.json)
WEB_SOURCES = (
    ("jobthai", fetch_jobthai, "boards.jobthai"),
    ("jobtopgun", fetch_jobtopgun, "boards.jobtopgun"),
)


# ------------------------------------------------------------------------ utils
def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _cell(value) -> str:
    """ค่าในช่องตาราง markdown: ตัด CR/LF ที่มาจากหน้าเว็บ/ข้อความ error ไม่ให้ตารางแตก."""
    text = "-" if value is None or value == "" else str(value)
    return re.sub(r"[\r\n]+", " ", text).strip() or "-"


def switches_for(preset: str | None = None) -> dict:
    data = load_json(CONFIG / "switches.json")
    name = preset or data.get("active") or "balanced"
    presets = data.get("presets") or {}
    if name not in presets:
        raise SystemExit(f"unknown preset: {name} (มี: {', '.join(presets)})")
    sw = dict(presets[name])
    sw["_preset"] = name
    return sw


def month_spend_usd(today: date, runs_dir: Path = RUNS) -> float:
    """ยอดสะสมเดือนนี้ อ่านจาก runs\\<YYYY-MM-DD>.md (ไม่มีไฟล์ = 0).

    อ่านบรรทัด 'cost_usd: $x.yz' เท่านั้น (ตัวเลขที่ run_all เขียนเอง).
    """
    if not runs_dir.is_dir():
        return 0.0
    total = 0.0
    prefix = f"{today:%Y-%m}"
    for path in runs_dir.glob("*.md"):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", path.stem) or not path.stem.startswith(prefix):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for value in re.findall(r"cost_usd:\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", text):
            total += float(value)
    return round(total, 4)


def clear_session() -> list[str]:
    """ลบ cookie/session artifacts ถ้ามี. ไม่แตะ config\\secrets.env (Tz วางเอง)."""
    removed: list[str] = []
    candidates = [
        DATA / "session",
        DATA / "cookies",
        CONFIG / "cookies.json",
        CONFIG / "storage_state.json",
    ]
    for path in candidates:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    child.unlink()
                    removed.append(str(child.relative_to(ROOT)))
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            path.rmdir()
            removed.append(str(path.relative_to(ROOT)))
        elif path.is_file():
            path.unlink()
            removed.append(str(path.relative_to(ROOT)))
    for pattern in ("*cookie*", "*session*"):
        for path in RAW.rglob(pattern):
            if path.is_file():
                path.unlink()
                removed.append(str(path.relative_to(ROOT)))
    return removed


# ----------------------------------------------------------------------- stages
def stage_fetch(today: date, sw: dict, keywords=None) -> dict:
    sites = [key for key in fetch_jobspy.SITE_MAP if sw.get(f"boards.{key}", True)]
    if not sites:
        return {"path": None, "per_source": {}, "errors": [], "cost_usd": 0.0,
                "logs": [], "skipped": "no_board_enabled"}
    return fetch_jobspy.run(keywords=keywords, sites=sites, day=today)


def stage_fetch_web(today: date, sw: dict, keywords=None) -> dict:
    """เว็บที่ HTML มาฝั่ง server (ฟรี ไม่ใช้ Apify): jobthai.com + jobtopgun.com.

    ทั้งคู่อยู่ขั้นเดียวกันก่อน normalize · เปิด/ปิดแยกด้วยสวิตช์เดิม boards.jobthai /
    boards.jobtopgun (strict = ปิดทั้งคู่) · แหล่งหนึ่งพัง/เน็ตล่ม = รายงานแล้วไปต่อ
    แหล่งอื่น ไม่ทำให้ pipeline ทั้งเส้นตาย
    """
    parts: list[dict] = []
    for source, module, switch in WEB_SOURCES:
        if not sw.get(switch, True):
            continue
        try:
            res = dict(module.run(keywords=keywords, day=today))
        except Exception as exc:  # เน็ต/ไลบรารีพัง = รายงาน ไม่ทำให้ pipeline ทั้งเส้นตาย
            parts.append({"path": None, "per_source": {}, "cost_usd": 0.0, "logs": [],
                          "total_rows": 0,
                          "errors": [f"{source}_web: {type(exc).__name__}: {exc}"]})
            continue
        res["per_source"] = {source: int(res.get("total_rows") or 0)}
        parts.append(res)
    if not parts:
        return {"path": None, "per_source": {}, "errors": [], "cost_usd": 0.0,
                "logs": [], "total_rows": 0, "skipped": "board_disabled"}
    return merge_fetch(*parts)


def merge_fetch(*parts: dict) -> dict:
    """รวมผลของหลาย fetcher เป็นก้อนเดียวที่ stage_log/summary ใช้."""
    out = {"path": None, "paths": [], "per_source": {}, "errors": [],
           "cost_usd": 0.0, "logs": [], "total_rows": 0, "params": None}
    for part in parts:
        if not part:
            continue
        if part.get("path"):
            out["paths"].append(part["path"])
            out["path"] = out["path"] or part["path"]
        if part.get("params") and out["params"] is None:
            out["params"] = part["params"]
        out["per_source"].update(part.get("per_source") or {})
        out["errors"].extend(part.get("errors") or [])
        out["cost_usd"] = round(out["cost_usd"] + float(part.get("cost_usd") or 0.0), 4)
        out["logs"].extend(part.get("logs") or [])
        out["total_rows"] += int(part.get("total_rows") or 0)
    return out


def load_raw_logs(today: date, name: str) -> dict:
    """--skip-fetch: อ่าน log ของไฟล์ดิบที่มีอยู่ (ไม่ยิงใหม่). ไม่มีไฟล์ = {}. """
    path = RAW / today.isoformat() / f"{name}.json"
    if not path.is_file():
        return {}
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    logs = [log for log in (payload.get("logs") or []) if isinstance(log, dict)]
    return {"path": str(path), "logs": logs, "cost_usd": 0.0, "per_source": {},
            "errors": [f"{log.get('keyword')}: {log.get('error')}"
                       for log in logs if log.get("error")],
            "total_rows": sum(int(log.get("results") or 0) for log in logs)}


def stage_normalize(today: date) -> dict:
    return norm.run(today)


def stage_build() -> dict:
    build_path = SRC / "build_page.py"
    if not build_path.is_file():
        return {"status": "page_skipped", "detail": "src\\build_page.py ยังไม่มี (coder-fast)"}
    proc = subprocess.run([sys.executable, str(build_path)], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=600)
    return {
        "status": "ok" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "").strip()[-2000:],
        "stderr": (proc.stderr or "").strip()[-2000:],
    }


def stage_log(today: date, fetch: dict, nres: dict, build: dict, sw: dict,
              notes: list[str]) -> Path:
    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / f"{today.isoformat()}.md"

    # ส่วนที่เขียนด้วยมือ (คำสั่งที่ยิงจริง/บทสรุป) อยู่ใต้ marker นี้ — รันซ้ำต้องไม่ทับ
    manual_marker = "## หลักฐานที่เติมด้วยมือ"
    manual = ""
    if path.is_file():
        try:
            old_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            old_text = ""
        if manual_marker in old_text:
            manual = old_text[old_text.index(manual_marker):].rstrip()

    logs = fetch.get("logs") or []
    by_source: dict[str, list[dict]] = {}
    for log in logs:
        by_source.setdefault(log["source"], []).append(log)

    lines = [
        f"# Run log {today.isoformat()}",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        f"- preset: {sw.get('_preset') or 'active'}",
        f"- cost_usd: ${fetch.get('cost_usd', 0.0):.2f}",
        "- session: T0 (cookieless) — ไม่มี cookie/session ในระบบ",
    ]
    params = fetch.get("params") or {}
    if params:
        lines += [
            "",
            "## พารามิเตอร์ที่ยิงจริง",
            "",
            f"- keywords: {', '.join(params.get('keywords') or []) or '-'}",
            f"- sites: {', '.join(params.get('sites') or []) or '-'}",
            f"- location: {params.get('location')} (per-site: {params.get('locations') or '-'})",
            f"- results_wanted/site: {params.get('results_wanted_per_site')} · hours_old: {params.get('hours_old')}",
        ]
    lines += [
        "",
        "",
        "## ต่อแหล่ง",
        "",
        "| แหล่ง | ยิงกี่คำ | ได้กี่งาน | cost_usd | error |",
        "|---|---|---|---|---|",
    ]
    for source in fetch_jobspy.SITE_MAP:
        entries = by_source.get(source, [])
        if not entries:
            lines.append(f"| {source} | 0 | 0 | $0.00 | ไม่ได้ยิงรอบนี้ (สวิตช์ปิด/ข้าม) |")
            continue
        errs = [f"{e['keyword']}: {e['error']}" for e in entries if e["error"]]
        got = sum(int(e["results"] or 0) for e in entries)
        lines.append(
            f"| {source} | {len(entries)} | {got} | "
            f"${sum(float(e.get('cost_usd') or 0) for e in entries):.2f} | "
            f"{' · '.join(errs) if errs else '-'} |"
        )
    for source in PAID_BOARDS:
        if sw.get(f"boards.{source}") and not by_source.get(source):
            lines.append(f"| {source} | 0 | 0 | $0.00 | wave 2: ยังไม่มี APIFY_TOKEN → no_token |")

    # jobthai + jobtopgun ผ่านเว็บ (ฟรี): คนละทางกับ Apify ข้างบน — แยกตารางให้เห็นทีละคำ/ทีละหน้า
    for source in ("jobthai", "jobtopgun"):
        web_logs = by_source.get(source, [])
        lines += ["", f"## {source} (เว็บ, ฟรี ไม่ใช้ Apify)", ""]
        if web_logs:
            kws = sorted({str(log.get("keyword")) for log in web_logs if log.get("keyword")})
            got = sum(int(log.get("results") or 0) for log in web_logs)
            notes = sorted({str(log.get("note")) for log in web_logs if log.get("note")})
            lines += [f"- keywords: {', '.join(_cell(k) for k in kws)}",
                      f"- รวม: {got} แถว · request ต่อหน้า: {len(web_logs)}"]
            if notes:
                lines.append(f"- note: {', '.join(_cell(n) for n in notes)}")
            lines += ["",
                      "| keyword | page | http | results | error |", "|---|---|---|---|---|"]
            for log in web_logs:
                lines.append(
                    f"| {_cell(log.get('keyword'))} | "
                    f"{_cell(log.get('page'))} | "
                    f"{_cell(log.get('http'))} | "
                    f"{int(log.get('results') or 0)} | {_cell(log.get('error'))} |")
        else:
            lines.append("- ไม่ได้ยิงรอบนี้ (สวิตช์ปิด/--skip-fetch ไม่มีไฟล์ดิบของวันนี้)")

    lines += [
        "",
        "## normalize (merge กับ data\\jobs.json เดิม)",
        "",
        f"- raw_rows: {nres.get('raw_rows')}",
        f"- jobs ในคลัง: {nres.get('jobs')}",
        f"- status gone: {nres.get('gone')}",
        f"- raw dir: `{nres.get('raw_dir')}`",
        "",
        "## build",
        "",
        f"- {build.get('status')}" + (f" — {build['detail']}" if build.get("detail") else ""),
    ]
    if build.get("stderr"):
        lines.append(f"- stderr: {build['stderr']}")
    if notes:
        lines += ["", "## หมายเหตุ", ""] + [f"- {n}" for n in notes]
    text = "\n".join(lines) + "\n"
    if manual:
        text += "\n" + manual + "\n"
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------------ main
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    today = date.today()
    notes: list[str] = []

    if "--clear-session" in argv:
        removed = clear_session()
        print(json.dumps({"clear_session": removed or "no session artifacts (T0)"},
                         ensure_ascii=False))
        # ล้างแล้ว "จบ" เสมอ เว้นแต่ผู้เรียกสั่งรันต่อชัดเจนด้วย --run
        # (--clear-session-only คงพฤติกรรมเดิม: จบเสมอ แม้มี --run)
        if "--clear-session-only" in argv or "--run" not in argv:
            return 0

    preset = None
    if "--preset" in argv:
        idx = argv.index("--preset")
        preset = argv[idx + 1] if idx + 1 < len(argv) else None
    sw = switches_for(preset)

    spend = month_spend_usd(today)
    if spend >= BUDGET_CAP_USD and any(sw.get(f"boards.{b}") for b in PAID_BOARDS):
        notes.append(f"หยุดเพราะเกินงบ: ยอดสะสมเดือนนี้ ${spend:.2f} ≥ ${BUDGET_CAP_USD:.2f}")
        print(json.dumps({"stopped": "budget", "spend_usd": spend}, ensure_ascii=False))
        fetch = {"path": None, "per_source": {}, "errors": [], "cost_usd": 0.0, "logs": []}
        nres = norm.run(today)  # ยังไม่ดึงใหม่ แต่คงคลังเดิมไว้
        build = stage_build()
        path = stage_log(today, fetch, nres, build, sw, notes)
        print(json.dumps({"log": str(path)}, ensure_ascii=False))
        return 0

    if "--skip-fetch" in argv:
        fetch = merge_fetch(load_raw_logs(today, "jobspy"), load_raw_logs(today, "jobthai"),
                            load_raw_logs(today, "jobtopgun"))
        notes.append("--skip-fetch: ใช้ผลดิบที่มีอยู่ ไม่ยิงใหม่")
    else:
        keywords = []
        for i, arg in enumerate(argv):
            if arg == "--keywords" and i + 1 < len(argv):
                keywords.append(argv[i + 1])
        # jobthai + jobtopgun (เว็บ) ก่อน แล้วค่อย JobSpy — ทั้งคู่อยู่ก่อน normalize และไม่พึ่ง Apify
        web = stage_fetch_web(today, sw, keywords or None)
        spy = stage_fetch(today, sw, keywords or None)
        fetch = merge_fetch(spy, web)
        fetch["web_path"] = web.get("path")
        fetch["web_total_rows"] = web.get("total_rows")

    nres = stage_normalize(today)
    build = stage_build()
    path = stage_log(today, fetch, nres, build, sw, notes)

    summary = {
        "fetch": {"path": fetch.get("path"), "per_source": fetch.get("per_source"),
                  "errors": fetch.get("errors"), "cost_usd": fetch.get("cost_usd")},
        "normalize": nres,
        "build": build.get("status"),
        "log": str(path),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if build.get("status") in ("ok", "page_skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
