#!/usr/bin/env python3
"""Val roadmap tool: load, validate, query, and visualize the roadmap graph.

Stdlib only (Python 3.11+). Subcommands:

  check            validate the roadmap data (ids, deps, cycles, ordering)
  build            write a self-contained viewer to .roadmap-site/index.html
  view             build, then serve on localhost and open a browser
  ready            list issues that can be started now
  path [--to ID | --stage S]   show the longest remaining dependency chain
  stats            summary counts
  stage S          what must be built to reach adoption stage S
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import re
import socketserver
import sys
import tomllib
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "roadmap"
DOCS_DIR = ROOT / "docs"
VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
SITE_DIR = ROOT / ".roadmap-site"

# Build ordering of milestones. The layer-pack track "L" opens after M4 and
# before autonomy, because packs need the Assist pipeline but not the policy
# engine, and later milestones may depend on packs.
MILESTONE_ORDER = ["M0", "M1", "M2", "M3", "M4", "L", "M5", "M6", "M7"]
SIZE_WEIGHT = {"S": 1, "M": 2, "L": 4}
VALID_TYPES = {"feature", "adr", "spike", "docs", "chore", "infra", "test"}
VALID_STATUS = {"todo", "doing", "done"}
ID_RE = re.compile(r"^E\d{2}-\d{2}$")
EPIC_RE = re.compile(r"^E\d{2}$")
DOC_ORDER = [
    "README",
    "plan/implementation-plan",
    "plan/rollout-plan",
    "design/architecture",
    "design/anti-shortcut-gates",
    "design/interview-decisions",
    "roadmap-format",
    "spec/original-spec",
]


class RoadmapError(Exception):
    """Raised when roadmap data is invalid."""


# --------------------------------------------------------------------------
# Loading and validation
# --------------------------------------------------------------------------


class Roadmap:
    def __init__(self, meta: dict, epics: list[dict], issues: list[dict]):
        self.milestones: list[dict] = meta.get("milestone", [])
        self.stages: list[dict] = meta.get("stage", [])
        self.epics = epics
        self.issues = issues
        self.by_id = {i["id"]: i for i in issues}
        self.epic_by_id = {e["id"]: e for e in epics}
        self.dependents: dict[str, list[str]] = defaultdict(list)
        for i in issues:
            for d in i["deps"]:
                if d in self.by_id:
                    self.dependents[d].append(i["id"])
        self.warnings: list[str] = []

    # -- computed graph properties ----------------------------------------

    def topo_order(self) -> list[str]:
        indeg = {i["id"]: len([d for d in i["deps"] if d in self.by_id]) for i in self.issues}
        queue = sorted(k for k, v in indeg.items() if v == 0)
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for m in sorted(self.dependents.get(n, [])):
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        return order

    def weight(self, issue_id: str) -> int:
        i = self.by_id[issue_id]
        return 0 if i["status"] == "done" else SIZE_WEIGHT[i["size"]]

    def depth(self) -> dict[str, int]:
        depth: dict[str, int] = {}
        for n in self.topo_order():
            ds = [depth[d] for d in self.by_id[n]["deps"] if d in depth]
            depth[n] = (max(ds) + 1) if ds else 0
        return depth

    def longest_chain(self, within: set[str] | None = None, to: str | None = None) -> list[str]:
        """Heaviest remaining-effort chain (optionally limited to a set / ending at `to`)."""
        best: dict[str, int] = {}
        prev: dict[str, str | None] = {}
        for n in self.topo_order():
            if within is not None and n not in within:
                continue
            cands = [d for d in self.by_id[n]["deps"] if d in best]
            if cands:
                p = max(cands, key=lambda d: (best[d], d))
                best[n] = best[p] + self.weight(n)
                prev[n] = p
            else:
                best[n] = self.weight(n)
                prev[n] = None
        if not best:
            return []
        end = to if to else max(best, key=lambda k: (best[k], k))
        chain = []
        cur: str | None = end
        while cur is not None:
            chain.append(cur)
            cur = prev.get(cur)
        return list(reversed(chain))

    def ancestors(self, ids: set[str]) -> set[str]:
        seen: set[str] = set()
        stack = list(ids)
        while stack:
            n = stack.pop()
            if n in seen or n not in self.by_id:
                continue
            seen.add(n)
            stack.extend(self.by_id[n]["deps"])
        return seen

    def descendants_count(self) -> dict[str, int]:
        memo: dict[str, set[str]] = {}

        def walk(n: str) -> set[str]:
            if n in memo:
                return memo[n]
            out: set[str] = set()
            for m in self.dependents.get(n, []):
                out.add(m)
                out |= walk(m)
            memo[n] = out
            return out

        sys.setrecursionlimit(10000)
        return {i["id"]: len(walk(i["id"])) for i in self.issues}

    def stage_issue_ids(self, stage: dict) -> set[str]:
        base = {i["id"] for i in self.issues if i["milestone"] in stage["requires"]}
        return self.ancestors(base)

    def ready(self) -> list[dict]:
        order = {m: n for n, m in enumerate(MILESTONE_ORDER)}
        down = self.descendants_count()
        out = [
            i
            for i in self.issues
            if i["status"] == "todo" and all(self.by_id[d]["status"] == "done" for d in i["deps"])
        ]
        out.sort(key=lambda i: (order[i["milestone"]], -down[i["id"]], i["id"]))
        return out

    def first_stage_for(self, milestone: str) -> str | None:
        for s in self.stages:
            if milestone in s["requires"]:
                return s["id"]
        return None


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise RoadmapError(f"{path.relative_to(ROOT)}: invalid TOML: {exc}") from exc


def load() -> Roadmap:
    meta = _read_toml(ROADMAP_DIR / "meta.toml")
    epics: list[dict] = []
    issues: list[dict] = []
    files = sorted((ROADMAP_DIR / "epics").glob("*.toml"))
    if not files:
        raise RoadmapError("no epic files found under roadmap/epics")
    for f in files:
        data = _read_toml(f)
        for e in data.get("epic", []):
            e = dict(e)
            e["file"] = str(f.relative_to(ROOT))
            epics.append(e)
        for i in data.get("issue", []):
            i = dict(i)
            i["file"] = str(f.relative_to(ROOT))
            issues.append(i)

    epic_by_id = {e.get("id"): e for e in epics}
    for i in issues:
        eid = str(i.get("id", ""))[:3]
        e = epic_by_id.get(eid, {})
        i["epic"] = eid
        i.setdefault("type", e.get("type", "feature"))
        i.setdefault("size", e.get("size", "M"))
        i.setdefault("milestone", e.get("milestone"))
        i.setdefault("lang", e.get("lang", []))
        i.setdefault("status", "todo")
        i.setdefault("deps", [])
        i.setdefault("acceptance", [])
        i.setdefault("summary", "")
    rm = Roadmap(meta, epics, issues)
    errors = validate(rm)
    if errors:
        raise RoadmapError("\n".join(errors))
    for i in issues:
        i["stage"] = rm.first_stage_for(i["milestone"])
    return rm


def validate(rm: Roadmap) -> list[str]:
    errs: list[str] = []
    ms_ids = [m["id"] for m in rm.milestones]
    if sorted(ms_ids) != sorted(MILESTONE_ORDER):
        errs.append(f"meta.toml milestones {ms_ids} must be exactly {MILESTONE_ORDER}")
    rank = {m: n for n, m in enumerate(MILESTONE_ORDER)}

    seen_epics: set[str] = set()
    for e in rm.epics:
        eid = e.get("id", "")
        if not EPIC_RE.match(eid):
            errs.append(f"{e['file']}: epic id {eid!r} must look like E07")
        if eid in seen_epics:
            errs.append(f"{e['file']}: duplicate epic id {eid}")
        seen_epics.add(eid)
        for key in ("title", "theme", "goal", "milestone"):
            if not e.get(key):
                errs.append(f"{eid}: epic missing '{key}'")
        if e.get("milestone") not in rank:
            errs.append(f"{eid}: unknown epic milestone {e.get('milestone')!r}")

    seen: set[str] = set()
    for i in rm.issues:
        iid = i.get("id", "")
        where = f"{i['file']}: {iid or '<no id>'}"
        if not ID_RE.match(iid):
            errs.append(f"{where}: id must look like E07-03")
            continue
        if iid in seen:
            errs.append(f"{where}: duplicate id")
        seen.add(iid)
        if i["epic"] not in seen_epics:
            errs.append(f"{where}: no epic {i['epic']} is defined")
        if not i.get("title"):
            errs.append(f"{where}: missing title")
        if not i["summary"]:
            errs.append(f"{where}: missing summary")
        if not i["acceptance"]:
            errs.append(f"{where}: needs at least one acceptance criterion")
        if i["milestone"] not in rank:
            errs.append(f"{where}: unknown milestone {i['milestone']!r}")
        if i["size"] not in SIZE_WEIGHT:
            errs.append(f"{where}: size must be one of {sorted(SIZE_WEIGHT)}")
        if i["type"] not in VALID_TYPES:
            errs.append(f"{where}: type {i['type']!r} not in {sorted(VALID_TYPES)}")
        if i["status"] not in VALID_STATUS:
            errs.append(f"{where}: status {i['status']!r} not in {sorted(VALID_STATUS)}")
        if i["size"] == "L":
            rm.warnings.append(f"{iid}: size L - consider splitting before starting")

    ids = {i["id"] for i in rm.issues if ID_RE.match(i.get("id", ""))}
    for i in rm.issues:
        iid = i.get("id", "")
        if iid not in ids:
            continue
        for d in i["deps"]:
            if d == iid:
                errs.append(f"{iid}: depends on itself")
            elif d not in ids:
                errs.append(f"{iid}: unknown dependency {d}")
            else:
                dm, im = rm.by_id[d]["milestone"], i["milestone"]
                if dm in rank and im in rank and rank[dm] > rank[im]:
                    errs.append(
                        f"{iid} ({im}) depends on {d} ({dm}), which is scheduled later - "
                        "move one of them or drop the dependency"
                    )
        if len(set(i["deps"])) != len(i["deps"]):
            errs.append(f"{iid}: duplicate entries in deps")

    for e in rm.epics:
        if not any(i["epic"] == e.get("id") for i in rm.issues):
            errs.append(f"{e.get('id')}: epic has no issues")

    if not errs:
        order = rm.topo_order()
        if len(order) != len(rm.issues):
            stuck = sorted(set(rm.by_id) - set(order))
            errs.append("dependency cycle involving: " + ", ".join(stuck[:12]) + (" ..." if len(stuck) > 12 else ""))

    for s in rm.stages:
        for m in s["requires"]:
            if m not in rank:
                errs.append(f"stage {s['id']}: unknown required milestone {m}")
    return errs


# --------------------------------------------------------------------------
# Markdown (small, safe subset) for docs
# --------------------------------------------------------------------------

_ID_LINK = re.compile(r"\b(E\d{2}(?:-\d{2})?)\b")


def _slug(text: str) -> str:
    s = re.sub(r"<[^>]+>", "", text).lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"\s+", "-", s.strip())


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _id_href(token: str) -> str:
    return f"#/issue/{token}" if "-" in token else f"#/epic/{token}"


def _inline(text: str, doc_id: str, known_docs: set[str], ids: set[str]) -> str:
    codes: list[str] = []

    def stash_code(m: re.Match) -> str:
        body = m.group(1)
        if re.fullmatch(r"E\d{2}(?:-\d{2})?", body) and body in ids:
            html = f'<a class="idlink" href="{_id_href(body)}"><code>{body}</code></a>'
        else:
            html = f"<code>{_esc(body)}</code>"
        codes.append(html)
        return f"\u0000{len(codes) - 1}\u0000"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = _esc(text)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:)", url):
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'
        if url.startswith("#"):
            return f'<a href="{url}">{label}</a>'
        path, _, frag = url.partition("#")
        if path.endswith(".md"):
            base = Path(doc_id).parent
            target = (DOCS_DIR / base / path).resolve() if doc_id != "README" else (ROOT / path).resolve()
            try:
                rel = target.relative_to(DOCS_DIR.resolve()).with_suffix("").as_posix()
            except ValueError:
                rel = target.relative_to(ROOT).with_suffix("").as_posix() if target.is_relative_to(ROOT) else path
            if rel in known_docs:
                return f'<a href="#/docs/{rel}">{label}</a>'
        return f"<span>{label}</span>"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w])_([^_\n]+)_(?![\w])", r"<em>\1</em>", text)

    def idl(m: re.Match) -> str:
        tok = m.group(1)
        return f'<a class="idlink" href="{_id_href(tok)}">{tok}</a>' if tok in ids else tok

    # Link bare ids, but not inside existing tags/attributes.
    parts = re.split(r"(<[^>]+>|\u0000\d+\u0000)", text)
    in_a = False
    out = []
    for p in parts:
        if p.startswith("<a "):
            in_a = True
        elif p == "</a>":
            in_a = False
        if p.startswith("<") or p.startswith("\u0000"):
            out.append(p)
        else:
            out.append(p if in_a else _ID_LINK.sub(idl, p))
    text = "".join(out)
    return re.sub(r"\u0000(\d+)\u0000", lambda m: codes[int(m.group(1))], text)


def render_markdown(src: str, doc_id: str, known_docs: set[str], ids: set[str]) -> tuple[str, str]:
    """Return (title, html)."""
    lines = src.replace("\r\n", "\n").split("\n")
    html: list[str] = []
    title = doc_id
    got_title = False
    i = 0
    inl = lambda t: _inline(t, doc_id, known_docs, ids)  # noqa: E731

    def flush_para(buf: list[str]) -> None:
        if buf:
            html.append("<p>" + inl(" ".join(s.strip() for s in buf)) + "</p>")
            buf.clear()

    para: list[str] = []
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush_para(para)
            lang = line.strip()[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            cls = f' class="lang-{_esc(lang)}"' if lang else ""
            html.append(f"<pre><code{cls}>{_esc(chr(10).join(code))}</code></pre>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush_para(para)
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1 and not got_title:
                title, got_title = re.sub(r"[`*]", "", text), True
            html.append(f'<h{level} id="{doc_id.replace("/", "-")}--{_slug(text)}">{inl(text)}</h{level}>')
            i += 1
            continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", line):
            flush_para(para)
            html.append("<hr>")
            i += 1
            continue
        if line.startswith(">"):
            flush_para(para)
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip(">").strip())
                i += 1
            html.append("<blockquote><p>" + inl(" ".join(quote)) + "</p></blockquote>")
            continue
        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            flush_para(para)
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(re.split(r"(?<!\\)\|", lines[i].strip().strip("|")))
                i += 1
            t = ["<div class='tablewrap'><table><thead><tr>"]
            t += [f"<th>{inl(h)}</th>" for h in header]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{inl(c.strip().replace(chr(92) + '|', '|'))}</td>" for c in r) + "</tr>")
            t.append("</tbody></table></div>")
            html.append("".join(t))
            continue
        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
        if lm:
            flush_para(para)
            items: list[tuple[int, bool, str]] = []
            while i < len(lines):
                lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if lm:
                    items.append((len(lm.group(1)) // 2, lm.group(2)[0].isdigit(), lm.group(3)))
                    i += 1
                elif lines[i].startswith("  ") and lines[i].strip() and items:
                    d, o, t = items[-1]
                    items[-1] = (d, o, t + " " + lines[i].strip())
                    i += 1
                else:
                    break
            stack: list[tuple[int, str]] = []
            out = []
            for depth, ordered, text in items:
                tag = "ol" if ordered else "ul"
                while stack and stack[-1][0] > depth:
                    out.append(f"</li></{stack.pop()[1]}>")
                if not stack or stack[-1][0] < depth:
                    out.append(f"<{tag}>")
                    stack.append((depth, tag))
                else:
                    out.append("</li>")
                out.append(f"<li>{inl(text)}")
            while stack:
                out.append(f"</li></{stack.pop()[1]}>")
            html.append("".join(out))
            continue
        if not line.strip():
            flush_para(para)
            i += 1
            continue
        para.append(line)
        i += 1
    flush_para(para)
    return title, "\n".join(html)


def load_docs(ids: set[str]) -> list[dict]:
    files: dict[str, Path] = {"README": ROOT / "README.md"}
    for p in sorted(DOCS_DIR.rglob("*.md")):
        files[p.relative_to(DOCS_DIR).with_suffix("").as_posix()] = p
    known = set(files)
    docs = []
    for doc_id, path in files.items():
        if not path.exists():
            continue
        title, body = render_markdown(path.read_text(encoding="utf-8"), doc_id, known, ids)
        group = doc_id.split("/")[0] if "/" in doc_id else "overview"
        docs.append({"id": doc_id, "title": title, "group": group, "html": body})
    order = {d: n for n, d in enumerate(DOC_ORDER)}
    docs.sort(key=lambda d: (order.get(d["id"], 99), d["id"]))
    return docs


# --------------------------------------------------------------------------
# Viewer data and build
# --------------------------------------------------------------------------


def build_payload(rm: Roadmap) -> dict:
    depth = rm.depth()
    crit = rm.longest_chain()
    ready = [i["id"] for i in rm.ready()]
    stages = []
    for s in rm.stages:
        ids = rm.stage_issue_ids(s)
        total = sum(SIZE_WEIGHT[rm.by_id[i]["size"]] for i in ids)
        remaining = sum(rm.weight(i) for i in ids)
        stages.append({**s, "issue_ids": sorted(ids), "effort": total, "remaining": remaining,
                       "critical": rm.longest_chain(within=ids)})
    epics = []
    for e in rm.epics:
        mine = [i for i in rm.issues if i["epic"] == e["id"]]
        spans = sorted({i["milestone"] for i in mine}, key=MILESTONE_ORDER.index)
        epics.append({**{k: v for k, v in e.items() if k != "file"}, "milestones": spans,
                      "count": len(mine), "done": sum(1 for i in mine if i["status"] == "done"),
                      "effort": sum(SIZE_WEIGHT[i["size"]] for i in mine)})
    issues = []
    for i in rm.issues:
        issues.append({
            "id": i["id"], "epic": i["epic"], "title": i["title"], "type": i["type"], "size": i["size"],
            "milestone": i["milestone"], "lang": i["lang"], "status": i["status"], "deps": i["deps"],
            "dependents": sorted(rm.dependents.get(i["id"], [])), "summary": i["summary"],
            "acceptance": i["acceptance"], "stage": i.get("stage"), "depth": depth[i["id"]],
        })
    ids = set(rm.by_id) | set(rm.epic_by_id)
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "milestoneOrder": MILESTONE_ORDER,
        "sizeWeight": SIZE_WEIGHT,
        "milestones": rm.milestones,
        "stages": stages,
        "epics": epics,
        "issues": issues,
        "critical": crit,
        "ready": ready,
        "docs": load_docs(ids),
    }


def build_site(rm: Roadmap) -> Path:
    payload = build_payload(rm)
    template = (VIEWER_DIR / "viewer.html").read_text(encoding="utf-8")
    css = (VIEWER_DIR / "viewer.css").read_text(encoding="utf-8")
    js = (VIEWER_DIR / "viewer.js").read_text(encoding="utf-8")
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    out = template.replace("/*__CSS__*/", css).replace("/*__JS__*/", js).replace("__ROADMAP_DATA__", data)
    SITE_DIR.mkdir(exist_ok=True)
    target = SITE_DIR / "index.html"
    target.write_text(out, encoding="utf-8")
    return target


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def cmd_check(rm: Roadmap, _args) -> int:
    for w in rm.warnings:
        print(f"warning: {w}")
    done = sum(1 for i in rm.issues if i["status"] == "done")
    print(f"ok: {len(rm.epics)} epics, {len(rm.issues)} issues, {sum(len(i['deps']) for i in rm.issues)} dependencies, "
          f"{done} done, graph is acyclic and milestone-consistent")
    return 0


def cmd_stats(rm: Roadmap, _args) -> int:
    total = sum(SIZE_WEIGHT[i["size"]] for i in rm.issues)
    print(f"epics {len(rm.epics)} | issues {len(rm.issues)} | effort points {total} (S=1, M=2, L=4)")
    print(f"{'milestone':<10}{'issues':>7}{'points':>8}  name")
    for mid in MILESTONE_ORDER:
        mine = [i for i in rm.issues if i["milestone"] == mid]
        name = next((m["name"] for m in rm.milestones if m["id"] == mid), "")
        print(f"{mid:<10}{len(mine):>7}{sum(SIZE_WEIGHT[i['size']] for i in mine):>8}  {name}")
    return 0


def cmd_ready(rm: Roadmap, args) -> int:
    rows = rm.ready()
    if args.milestone:
        rows = [r for r in rows if r["milestone"] == args.milestone]
    for i in rows[: args.limit]:
        print(f"{i['id']}  {i['milestone']:<3} {i['size']}  {i['title']}")
    print(f"-- {len(rows)} ready (showing up to {args.limit})")
    return 0


def cmd_path(rm: Roadmap, args) -> int:
    within = None
    to = None
    label = "whole roadmap"
    if args.stage:
        st = next((s for s in rm.stages if s["id"] == args.stage), None)
        if not st:
            print(f"unknown stage {args.stage}", file=sys.stderr)
            return 2
        within, label = rm.stage_issue_ids(st), f"stage {st['id']} ({st['name']})"
    if args.to:
        if args.to not in rm.by_id:
            print(f"unknown issue {args.to}", file=sys.stderr)
            return 2
        within, to, label = rm.ancestors({args.to}), args.to, f"to {args.to}"
    chain = rm.longest_chain(within=within, to=to)
    print(f"Longest remaining chain - {label}")
    total = 0
    for n, iid in enumerate(chain, 1):
        i = rm.by_id[iid]
        total += rm.weight(iid)
        print(f"{n:>3}. {iid}  {i['milestone']:<3} {i['size']}  {i['title']}")
    print(f"-- {len(chain)} issues, {total} effort points on the critical chain")
    return 0


def cmd_stage(rm: Roadmap, args) -> int:
    st = next((s for s in rm.stages if s["id"] == args.stage), None)
    if not st:
        print(f"unknown stage {args.stage}", file=sys.stderr)
        return 2
    ids = rm.stage_issue_ids(st)
    pts = sum(SIZE_WEIGHT[rm.by_id[i]["size"]] for i in ids)
    print(f"{st['id']} {st['name']}: {st['summary']}")
    print(f"requires milestones {', '.join(st['requires'])} -> {len(ids)} issues, {pts} effort points")
    by_epic: dict[str, int] = defaultdict(int)
    for i in ids:
        by_epic[rm.by_id[i]["epic"]] += 1
    for e in rm.epics:
        if by_epic.get(e["id"]):
            print(f"  {e['id']} {e['title']}: {by_epic[e['id']]}")
    return 0


def cmd_build(rm: Roadmap, _args) -> int:
    target = build_site(rm)
    print(f"built {target.relative_to(ROOT)} ({target.stat().st_size // 1024} KiB)")
    return 0


def cmd_view(rm: Roadmap, args) -> int:
    target = build_site(rm)
    handler = functools.partial(_QuietHandler, directory=str(target.parent))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"
        print(f"serving {target.relative_to(ROOT)} at {url}  (Ctrl-C to stop)")
        if not args.no_open:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a):  # noqa: D401
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="val-roadmap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    sub.add_parser("stats")
    sub.add_parser("build")
    v = sub.add_parser("view")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--no-open", action="store_true")
    r = sub.add_parser("ready")
    r.add_argument("--milestone")
    r.add_argument("--limit", type=int, default=25)
    pa = sub.add_parser("path")
    pa.add_argument("--to")
    pa.add_argument("--stage")
    st = sub.add_parser("stage")
    st.add_argument("stage")
    args = p.parse_args(argv)
    try:
        rm = load()
    except RoadmapError as exc:
        print(f"roadmap invalid:\n{exc}", file=sys.stderr)
        return 1
    return {
        "check": cmd_check, "stats": cmd_stats, "build": cmd_build, "view": cmd_view,
        "ready": cmd_ready, "path": cmd_path, "stage": cmd_stage,
    }[args.cmd](rm, args)


if __name__ == "__main__":
    sys.exit(main())
