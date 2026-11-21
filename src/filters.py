"""filters.py — ให้คะแนน + ตัดด้วย must_not / include / salary_min / พื้นที่
ใช้ร่วมกันระหว่าง src\\build_page.py (ตอน build) และเทสต์

กติกา (brief §3/§6): ไม่ชัด = null/[] ห้ามเดา · ห้ามแปล title/company/district
ไม่อ่านไฟล์ใด ๆ นอกจาก config\\filters.json (path มาจาก __file__ ไม่มี absolute path)

API หลัก
    load_config(path=None) -> dict
    score(job, cfg=None) -> int                     คะแนน (ไม่ตัดอะไร)
    drop_reason(job, cfg=None, switches=None) -> str | None   None = ผ่าน
    should_drop(job, ...) -> bool
    passes(job, ...) -> bool
    apply_filters(jobs, cfg=None, switches=None, include_mode="filter") -> list[dict]
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILTERS_PATH = ROOT / "config" / "filters.json"
SWITCHES_PATH = ROOT / "config" / "switches.json"


# --------------------------------------------------------------------------- io
@lru_cache(maxsize=4)
def load_config(path: str | None = None) -> dict:
    """อ่าน config\\filters.json (cache ตาม path)."""
    p = Path(path) if path else FILTERS_PATH
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=4)
def load_switches(path: str | None = None) -> dict:
    p = Path(path) if path else SWITCHES_PATH
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("switches", {})


# ----------------------------------------------------------------------- helpers
def _s(value) -> str:
    return "" if value is None else str(value)


def _rx(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


@lru_cache(maxsize=2048)
def _compiled(pattern: str) -> re.Pattern:
    return _rx(pattern)


def job_text(job: dict) -> str:
    """ข้อความที่ใช้ตรวจคำ: title + company + description + raw_text + skills.

    skills = คำที่ src\\normalize.py สกัดไว้ (รวมคำที่อ่านได้จาก description) — schema ไม่เก็บ
    description ดิบ (22 คีย์คงเดิม) ทางเดียวที่คำใน description จะมีผลกับ include คือทาง skills นี้
    (ไม่แปลงอะไร: ใช้ค่าที่เก็บไว้ตามเดิม).
    """
    skills = job.get("skills") or []
    if isinstance(skills, str):
        skills = [skills]
    parts = [
        _s(job.get("title")),
        _s(job.get("company")),
        _s(job.get("description")),
        _s(job.get("raw_text")),
        " ".join(s for s in skills if isinstance(s, str)),
    ]
    return "\n".join(p for p in parts if p)


def _is_ascii(text: str) -> bool:
    return all(ord(ch) < 128 for ch in text)


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _term_pattern(term: str) -> str | None:
    """คำใน include/must_not → regex ที่แมตช์ตามชนิดของคำ.

    - ASCII ล้วน (cloud / aws / intern / sales / network engineer) → \\b ทั้งสองข้าง:
      "cloud" จึงไม่จับ "Gushcloud"/"Cloudbeds" และ "intern" ไม่จับ "internal"
    - มีอักขระนอก ASCII (คลาวด์ / ฝึกงาน / แรงงาน) → substring เพราะ \\b ของ Python
      ผูกกับ "คำ" ที่คั่นด้วยช่องว่างซึ่งข้อความไทยไม่มี → \\b ใช้กับภาษาไทยไม่ได้
    - หลายคำ → ช่องว่างภายในเป็น \\s+ และขอบเขตคำอยู่ที่ปลายวลีทั้งสองข้าง
    - ปลายที่เป็นอักขระ non-word (pre-sales) ไม่ใส่ \\b ด้านนั้น (\\b ต้องมี word char ข้างหนึ่ง)
    """
    words = term.split()
    if not words:
        return None
    body = r"\s+".join(re.escape(w) for w in words)
    if not _is_ascii(term):
        return body
    left = r"\b" if _is_word_char(words[0][0]) else ""
    right = r"\b" if _is_word_char(words[-1][-1]) else ""
    return left + body + right


def _match_any(patterns, text: str) -> str | None:
    for pat in patterns or []:
        if _compiled(pat).search(text):
            return pat
    return None


# ------------------------------------------------------------------- relevance
def matches_include(job: dict, cfg: dict | None = None) -> bool:
    """อยู่ในขอบเขตที่สนใจไหม. include ว่าง = ถือว่าผ่าน (เก็บกว้าง กรองแคบ)."""
    cfg = cfg or load_config()
    inc = cfg.get("include") or {}
    titles = [t for t in (inc.get("titles") or []) if t]
    any_of = [t for t in (inc.get("any_of") or []) if t]
    title = _s(job.get("title"))
    text = job_text(job)
    if titles and not any(_compiled(p).search(title) for p in _ci(titles)):
        return False
    if any_of:
        return any(_compiled(p).search(text) for p in _ci(any_of)) or bool(
            _match_any(inc.get("regex") or [], text)
        )
    return True


def _ci(terms):
    """คำธรรมดา → regex ที่ไม่สนตัวพิมพ์/ช่องว่างซ้อน และมีขอบเขตคำตามชนิดของคำ."""
    for term in terms:
        pat = _term_pattern(term) if term else None
        if pat:
            yield pat


def must_not_hit(job: dict, cfg: dict | None = None) -> str | None:
    """คืนคำที่ทำให้ถูกตัด (ตรวจ title เท่านั้น — ไม่ตัดจาก raw_text ของ FB)."""
    cfg = cfg or load_config()
    mn = cfg.get("must_not") or {}
    title = _s(job.get("title"))
    for term in mn.get("titles") or []:
        pat = _term_pattern(term) if term else None
        if pat and _compiled(pat).search(title):
            return term
    return _match_any(mn.get("regex") or [], title)


def salary_floor_hit(job: dict, cfg: dict | None = None) -> bool:
    """ตัดเมื่อรู้เงินเดือนแล้วเพดานบนยังต่ำกว่าพื้นที่ตั้งไว้ (ไม่รู้ = ไม่ตัด)."""
    cfg = cfg or load_config()
    floor = cfg.get("salary_min") or 0
    if not floor:
        return False
    top = job.get("salary_max")
    if top is None:
        return False
    try:
        return float(top) < float(floor)
    except (TypeError, ValueError):
        return False


def province_tokens(cfg: dict | None = None) -> dict:
    """ชื่อจังหวัดที่รู้จัก: config\\filters.json → {"bangkok": [...], "perimeter": [...], "other": [...]}.

    ใช้ provinces เป็นหลัก (ชุดเดียวกับที่ src\\normalize.py ใช้ตัดสิน province) และถอยไปใช้
    area เมื่อไฟล์ config ไม่มี provinces. อยู่นอกรายการนี้ = ไม่ใช่จังหวัด → ไม่ใช่หลักฐานการตัด."""
    cfg = cfg or load_config()
    prov = cfg.get("provinces") or {}
    groups = {}
    for key in ("bangkok", "perimeter", "other"):
        names = prov.get(key)
        if isinstance(names, str):
            names = [names]
        groups[key] = [_s(n) for n in (names or []) if _s(n).strip()]
    if not any(groups.values()):
        area = cfg.get("area") or {}
        groups["bangkok"] = [_s(n) for n in (area.get("bangkok") or []) if _s(n).strip()]
        groups["perimeter"] = [_s(n) for n in (area.get("perimeter") or []) if _s(n).strip()]
        groups["other"] = []
    return groups


def _province_in(province: str, names) -> bool:
    return any(_s(n).strip().casefold() and _s(n).strip().casefold() in province
               for n in names or [])


def area_hit(job: dict, cfg: dict | None = None, switches: dict | None = None) -> bool:
    """True = อยู่นอกพื้นที่. ตัดสินจาก province ที่เป็นชื่อจังหวัดที่รู้จักเท่านั้น.

    กรุงเทพ → อยู่ในพื้นที่ · ปริมณฑล → ตามสวิตช์ area.include_perimeter ·
    จังหวัดอื่นที่รู้จัก → นอกพื้นที่ · province null/ว่าง/ไม่รู้จัก → ไม่ตัด (False)
    location/district ดิบไม่ถูกใช้เป็นหลักฐานการตัด (ใบงาน §3 ห้ามเดา): แถวที่ province = null
    และ location = "40, Thailand" จึงหลุดการตัดนี้ไปติดป้าย "พื้นที่ไม่ระบุ" บนหน้าเว็บแทน.
    """
    cfg = cfg or load_config()
    sw = switches if switches is not None else load_switches()
    province = _s(job.get("province")).strip().casefold()
    if not province:
        return False
    groups = province_tokens(cfg)
    if _province_in(province, groups.get("bangkok")):
        return False
    if _province_in(province, groups.get("perimeter")):
        return not bool(sw.get("area.include_perimeter"))
    if _province_in(province, groups.get("other")):
        if sw.get("area.remote_anywhere") and _job_is_remote_anywhere(job, cfg):
            return False
        return True
    return False


def _job_is_remote_anywhere(job: dict, cfg: dict) -> bool:
    pats = (cfg.get("remote_anywhere") or {}).get("patterns") or []
    return bool(_match_any(pats, job_text(job)))


# ----------------------------------------------------------------------- score
def score(job: dict, cfg: dict | None = None) -> int:
    """คะแนนเรียงลำดับ (ไม่มีผลต่อการตัด)."""
    cfg = cfg or load_config()
    boost = cfg.get("boost") or {}
    total = 0

    skills = [s for s in job.get("skills") or [] if isinstance(s, str)]
    for term, weight in (boost.get("skills") or {}).items():
        if term.lower() in [s.lower() for s in skills]:
            total += int(weight)

    sen = job.get("seniority")
    if sen:
        total += int((boost.get("seniority") or {}).get(sen, 0))

    mode = job.get("work_mode")
    if mode:
        total += int((boost.get("work_mode") or {}).get(mode, 0))

    src_boost = boost.get("sources") or {}
    if job.get("sources"):
        total += max(int(src_boost.get(s, 0)) for s in job["sources"])
    elif job.get("source"):
        total += int(src_boost.get(job["source"], 0))

    if matches_include(job, cfg):
        total += 2
    return total


# ------------------------------------------------------------------------ drop
def drop_reason(
    job: dict,
    cfg: dict | None = None,
    switches: dict | None = None,
    include_mode: str = "filter",
) -> str | None:
    """เหตุผลที่ตัดแถวนี้ หรือ None ถ้าผ่าน."""
    cfg = cfg or load_config()
    hit = must_not_hit(job, cfg)
    if hit:
        return f"must_not:{hit}"
    if salary_floor_hit(job, cfg):
        return "salary_below_min"
    if area_hit(job, cfg, switches):
        return "area_outside"
    if include_mode == "filter" and not matches_include(job, cfg):
        return "include_miss"
    return None


def should_drop(job: dict, **kwargs) -> bool:
    return drop_reason(job, **kwargs) is not None


def passes(job: dict, **kwargs) -> bool:
    return drop_reason(job, **kwargs) is None


def apply_filters(
    jobs,
    cfg: dict | None = None,
    switches: dict | None = None,
    include_mode: str = "filter",
):
    """ตัดแล้วเรียงตามคะแนนมาก→น้อย (คงลำดับเดิมเมื่อคะแนนเท่ากัน)."""
    cfg = cfg or load_config()
    kept = []
    for idx, job in enumerate(jobs):
        if drop_reason(job, cfg, switches, include_mode) is None:
            kept.append((-score(job, cfg), idx, job))
    kept.sort(key=lambda t: (t[0], t[1]))
    return [job for _, _, job in kept]


# alias ที่ชื่ออื่นอาจเรียก
score_job = score
filter_jobs = apply_filters
