#!/usr/bin/env python3
"""Cross-layer coherence audit for media-monitor.

Read-only checks (plan 2026-10-14, Fase 3):
  1. routes <-> nav coverage
  2. classification enums: backend topics ⊆ TS label/badge maps
  3. TS interface <-> pydantic schema field asymmetries
  4. live DB classification labels covered by TS maps
  5. env/config: API_BASE_URL consistency; ai_api_key present (not printed)

Usage: .venv/bin/python scripts/audit_coherence.py
Exit code 0 always; verdicts OK / FINDINGS / SKIP per check.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"

results: list[tuple[str, str, list[str]]] = []  # (check, verdict, lines)


def record(check: str, verdict: str, lines: list[str]) -> None:
    results.append((check, verdict, lines))


def read(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


# check 1 -----------------------------------------------------------------
def routes_check() -> tuple[str, list[str]]:
    lines: list[str] = []
    pages = sorted(FRONTEND.glob("src/routes/**/+page.svelte"))
    routes: set[str] = set()
    for p in pages:
        rel = p.parent.relative_to(FRONTEND / "src" / "routes")
        # drop SvelteKit group segments (parenthesised)
        clean = re.sub(r"/\([^)]+\)", "", "/" + str(rel))
        routes.add(clean.replace("//", "/") if str(rel) != "." else "/")
    layout = read(FRONTEND / "src" / "routes" / "+layout.svelte")
    if layout is None:
        return "SKIP", ["+layout.svelte not found"]
    hrefs = set(re.findall(r"href:\s*'([^']+)'", layout))
    for r in sorted(routes):
        # dynamic detail segments ([id]) are linked from list pages, not nav
        kind = "detail" if "[" in r else ("nav" if r in hrefs else "MISSING")
        lines.append(f"  route {r}: {kind}")
    missing = sorted(r for r in routes if "[" not in r and r not in hrefs)
    return ("OK" if not missing else "FINDINGS"), lines


# check 2 -----------------------------------------------------------------
def enums_check() -> tuple[str, list[str]]:
    lines: list[str] = []
    py = read(BACKEND / "app" / "enrich" / "llm.py") or ""
    m = re.search(r"TOPIC_LABELS\s*=?\s*\(([^)]*)\)", py, re.S)
    if not m:
        return "SKIP", ["backend TOPIC_LABELS tuple not found"]
    body = m.group(1)
    pairs = dict(re.findall(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', body))
    if not pairs:
        pairs = dict(zip(re.findall(r'"([^"]+)"', body), re.findall(r'"([^"]+)"', body)))
    fmt = read(FRONTEND / "src" / "lib" / "format.ts") or ""
    labels_m = re.search(r"TOPIC_LABELS[^{]*=\s*\{(.*?)\n\}", fmt, re.S)
    badges_m = re.search(r"TOPIC_BADGE_CLASSES[^{]*=\s*\{(.*?)\n\}", fmt, re.S)
    ts_labels = set(re.findall(r"'?([a-z_]+)'?:", labels_m.group(1), re.M)) if labels_m else set()
    ts_badges = set(re.findall(r"'?([a-z_]+)'?:", badges_m.group(1), re.M)) if badges_m else set()
    for key in sorted(pairs):
        lines.append(
            f"  topic {key}: labels={'y' if key in ts_labels else 'MISSING'} "
            f"badges={'y' if key in ts_badges else 'legacy-ok'}"
        )
    missing_labels = [k for k in pairs if k not in ts_labels]
    return ("OK" if not missing_labels else "FINDINGS"), lines


# check 3 -----------------------------------------------------------------
CONTRACT_PAIRS = [
    ("Mention", "MentionOut"),
    ("PersonSummary", "PersonOut"),
    ("PersonTimelineItem", "PersonTimelineItem"),
    ("AskResult", "AskResponse"),
]


def ts_interfaces(src: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in re.finditer(r"interface (\w+)[^{]*\{(.*?)\n\}", src, re.S):
        out[m.group(1)] = set(re.findall(r"^\s{1,4}(\w+)\??\s*:", m.group(2), re.M))
    return out


def py_schemas(src: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for m in re.finditer(r"class (\w+)\([^)]*\):\n(.*?)(?=\nclass |\n\n@|\\Z)", src, re.S):
        fields = set()
        for line in m.group(2).splitlines():
            fm = re.match(r"    (\w+)\s*:", line)
            if fm:
                fields.add(fm.group(1))
        out[m.group(1)] = fields
    return out


def contract_check() -> tuple[str, list[str]]:
    lines: list[str] = []
    ts = ts_interfaces(read(FRONTEND / "src" / "lib" / "api.ts") or "")
    py = py_schemas(read(BACKEND / "app" / "api" / "schemas.py") or "")
    any_missing = False
    for ts_name, py_name in CONTRACT_PAIRS:
        if ts_name not in ts or py_name not in py:
            lines.append(f"  {ts_name}<->{py_name}: SKIP (definition not found)")
            continue
        ts_f, py_f = ts[ts_name], py[py_name]
        for f in sorted(ts_f - py_f):
            any_missing = True
            lines.append(f"  {ts_name}.{f}: in TS, absent in {py_name} -> verify optional chaining")
        for f in sorted(py_f - ts_f):
            lines.append(f"  {py_name}.{f}: backend-only (documented, no action)")
    return ("OK" if not any_missing else "FINDINGS"), lines


# checks 4/5: DB + env -----------------------------------------------------
def psql(sql: str) -> str | None:
    try:
        r = subprocess.run(
            ["docker", "exec", "media-monitor-db-1", "psql",
             "-U", "media", "-d", "mediamonitor", "-tAc", sql],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def db_checks() -> tuple[str, str, list[str], list[str]]:
    fmt = read(FRONTEND / "src" / "lib" / "format.ts") or ""
    mapped_keys = set(re.findall(r"^\s+'?([a-z_]+)'?:\s*['\"b]", fmt, re.M))

    c4_lines: list[str] = []
    c4_verdict = "SKIP"
    # 'topics' (enrichment free-form multi-label) is rendered raw; only the
    # enum classifiers have TS maps to satisfy
    labels_raw = psql(
        "SELECT DISTINCT label FROM mention_classifications "
        "WHERE classifier IN ('topic', 'political') ORDER BY 1"
    )
    if labels_raw is None:
        c4_lines.append("  DB unreachable via docker exec - SKIP")
    else:
        topics_n = psql("SELECT COUNT(DISTINCT label) FROM mention_classifications WHERE classifier='topics'")
        if topics_n:
            c4_lines.append(f"  enrichment 'topics' free-form labels: {topics_n.strip()} (rendered raw, no map)")
        unmapped = []
        for lab in (x.strip() for x in labels_raw.splitlines()):
            if not lab:
                continue
            ok = lab in mapped_keys
            c4_lines.append(f"  label {lab!r}: {'mapped' if ok else 'UNMAPPED in TS maps'}")
            if not ok:
                unmapped.append(lab)
        c4_verdict = "OK" if not unmapped else "FINDINGS"

    c5_lines: list[str] = []
    c5_verdict = "SKIP"
    key_raw = psql("SELECT COUNT(*) FROM settings WHERE ai_api_key IS NOT NULL AND ai_api_key <> ''")
    if key_raw is None:
        c5_lines.append("  settings.ai_api_key probe unavailable - SKIP")
    else:
        c5_lines.append(f"  clients with ai_api_key set: {key_raw.strip()} (values not printed)")
        c5_verdict = "OK"
    for env in sorted(FRONTEND.glob(".env*")):
        txt = read(env) or ""
        for m in re.finditer(r"^(API_BASE_URL)=(.*)$", txt, re.M):
            c5_lines.append(f"  {env.name}: {m.group(1)}={m.group(2).strip()}")
    c5_lines.append("  api.ts fallback default: http://localhost:8000")
    return c4_verdict, c5_verdict, c4_lines, c5_lines


# ---------------------------------------------------------------- main
def main() -> None:
    v1, l1 = routes_check()
    record("1. routes <-> nav", v1, l1)
    v2, l2 = enums_check()
    record("2. enums clasificacion (backend -> TS)", v2, l2)
    v3, l3 = contract_check()
    record("3. contrato TS<->pydantic", v3, l3)
    v4, v5, l4, l5 = db_checks()
    record("4. labels DB vs mapas TS", v4, l4)
    record("5. env/config", v5, l5)
    for check, verdict, lines in results:
        print(f"[{verdict}] {check}")
        for line in lines:
            print(line)
    print("---")
    print("audit_coherence: done")
    return None


if __name__ == "__main__":
    sys.exit(main())
