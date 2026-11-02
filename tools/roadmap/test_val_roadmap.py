"""Unit tests for the roadmap tool. Stdlib only: python3 -m unittest discover -s tools/roadmap"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import val_roadmap as vr  # noqa: E402


def make(issues: list[dict], epics: list[dict] | None = None, stages: list[dict] | None = None) -> vr.Roadmap:
    """Build a Roadmap from compact issue dicts, applying the same defaults as load()."""
    epics = epics or [
        {"id": "E01", "title": "One", "theme": "platform", "goal": "g", "milestone": "M1", "file": "t.toml"},
        {"id": "E02", "title": "Two", "theme": "assess", "goal": "g", "milestone": "M2", "file": "t.toml"},
    ]
    meta = {
        "milestone": [{"id": m, "name": m, "goal": "g"} for m in vr.MILESTONE_ORDER],
        "stage": stages or [],
    }
    full = []
    for i in issues:
        i = dict(i)
        i.setdefault("file", "t.toml")
        i["epic"] = i["id"][:3]
        i.setdefault("title", "t")
        i.setdefault("type", "feature")
        i.setdefault("size", "M")
        i.setdefault("milestone", "M1")
        i.setdefault("lang", [])
        i.setdefault("status", "todo")
        i.setdefault("deps", [])
        i.setdefault("summary", "s")
        i.setdefault("acceptance", ["a"])
        full.append(i)
    return vr.Roadmap(meta, epics, full)


class ValidateTests(unittest.TestCase):
    def test_valid_graph_has_no_errors(self):
        rm = make([{"id": "E01-01"}, {"id": "E01-02", "deps": ["E01-01"]}, {"id": "E02-01", "milestone": "M2", "deps": ["E01-02"]}])
        self.assertEqual(vr.validate(rm), [])

    def test_unknown_dependency(self):
        rm = make([{"id": "E01-01", "deps": ["E09-99"]}, {"id": "E02-01", "milestone": "M2"}])
        self.assertTrue(any("unknown dependency E09-99" in e for e in vr.validate(rm)))

    def test_self_dependency(self):
        rm = make([{"id": "E01-01", "deps": ["E01-01"]}, {"id": "E02-01", "milestone": "M2"}])
        self.assertTrue(any("depends on itself" in e for e in vr.validate(rm)))

    def test_cycle_detected(self):
        rm = make([
            {"id": "E01-01", "deps": ["E01-02"]},
            {"id": "E01-02", "deps": ["E01-01"]},
            {"id": "E02-01", "milestone": "M2"},
        ])
        errs = vr.validate(rm)
        self.assertTrue(any("cycle" in e for e in errs), errs)

    def test_dependency_on_later_milestone_rejected(self):
        rm = make([{"id": "E01-01", "milestone": "M1", "deps": ["E02-01"]}, {"id": "E02-01", "milestone": "M2"}])
        self.assertTrue(any("scheduled later" in e for e in vr.validate(rm)))

    def test_layer_track_ordering(self):
        # L sits between M4 and M5: M5 may depend on L, L may not depend on M5.
        ok = make([{"id": "E01-01", "milestone": "L"}, {"id": "E02-01", "milestone": "M5", "deps": ["E01-01"]}])
        self.assertEqual(vr.validate(ok), [])
        bad = make([{"id": "E01-01", "milestone": "M5"}, {"id": "E02-01", "milestone": "L", "deps": ["E01-01"]}])
        self.assertTrue(any("scheduled later" in e for e in vr.validate(bad)))

    def test_duplicate_ids_and_bad_fields(self):
        rm = make([{"id": "E01-01"}, {"id": "E01-01"}, {"id": "E02-01", "milestone": "M2", "size": "XL", "status": "wip"}])
        errs = "\n".join(vr.validate(rm))
        self.assertIn("duplicate id", errs)
        self.assertIn("size must be one of", errs)
        self.assertIn("status 'wip'", errs)

    def test_missing_acceptance_and_epic_without_issues(self):
        rm = make([{"id": "E01-01", "acceptance": []}])
        errs = "\n".join(vr.validate(rm))
        self.assertIn("acceptance criterion", errs)
        self.assertIn("E02: epic has no issues", errs)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.rm = make([
            {"id": "E01-01", "size": "S"},
            {"id": "E01-02", "size": "M", "deps": ["E01-01"]},
            {"id": "E01-03", "size": "L", "deps": ["E01-01"]},
            {"id": "E02-01", "size": "S", "milestone": "M2", "deps": ["E01-02", "E01-03"]},
        ])

    def test_topo_order_respects_dependencies(self):
        order = self.rm.topo_order()
        self.assertEqual(len(order), 4)
        self.assertLess(order.index("E01-01"), order.index("E01-03"))
        self.assertLess(order.index("E01-03"), order.index("E02-01"))

    def test_longest_chain_prefers_heavier_branch(self):
        self.assertEqual(self.rm.longest_chain(), ["E01-01", "E01-03", "E02-01"])

    def test_done_work_costs_nothing(self):
        self.rm.by_id["E01-03"]["status"] = "done"
        self.assertEqual(self.rm.longest_chain(), ["E01-01", "E01-02", "E02-01"])

    def test_chain_to_target_and_within(self):
        self.assertEqual(self.rm.longest_chain(within=self.rm.ancestors({"E01-02"}), to="E01-02"), ["E01-01", "E01-02"])

    def test_depth(self):
        d = self.rm.depth()
        self.assertEqual((d["E01-01"], d["E01-02"], d["E02-01"]), (0, 1, 2))

    def test_ready_queue(self):
        self.assertEqual([i["id"] for i in self.rm.ready()], ["E01-01"])
        self.rm.by_id["E01-01"]["status"] = "done"
        self.assertEqual({i["id"] for i in self.rm.ready()}, {"E01-02", "E01-03"})

    def test_stage_closure_includes_transitive_deps(self):
        stage = {"id": "S9", "name": "n", "requires": ["M2"]}
        self.assertEqual(self.rm.stage_issue_ids(stage), {"E02-01", "E01-02", "E01-03", "E01-01"})


class MarkdownTests(unittest.TestCase):
    def render(self, src: str, ids=frozenset({"E07-03", "E07"})) -> str:
        return vr.render_markdown(src, "design/x", {"design/x", "design/y"}, set(ids))[1]

    def test_title_and_escaping(self):
        title, html = vr.render_markdown("# Hello <b>\n\ntext & more", "x", {"x"}, set())
        self.assertEqual(title, "Hello <b>")
        self.assertIn("&lt;b&gt;", html)
        self.assertIn("text &amp; more", html)

    def test_ids_are_linked_but_not_unknown_ones(self):
        html = self.render("See E07-03 and E99-01, and `E07`.")
        self.assertIn('href="#/issue/E07-03"', html)
        self.assertIn('href="#/epic/E07"', html)
        self.assertNotIn("E99-01</a>", html)

    def test_relative_doc_links_resolve(self):
        self.assertIn('href="#/docs/design/y"', self.render("[y](y.md)"))

    def test_code_block_is_not_interpreted(self):
        html = self.render("```\nE07-03 <script>\n```")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("idlink", html)

    def test_table_and_list(self):
        html = self.render("| a | b |\n|---|---|\n| 1 | 2 |\n\n- x\n- y\n")
        self.assertIn("<table>", html)
        self.assertIn("<li>x", html)

    def test_external_links_are_safe(self):
        html = self.render("[x](https://example.com)")
        self.assertIn('rel="noopener noreferrer"', html)


class RealRoadmapTests(unittest.TestCase):
    """The committed roadmap must always be valid; this is what CI runs."""

    @classmethod
    def setUpClass(cls):
        cls.rm = vr.load()

    def test_loads_and_is_acyclic(self):
        self.assertEqual(len(self.rm.topo_order()), len(self.rm.issues))

    def test_every_stage_requirement_is_a_known_milestone(self):
        ids = {m["id"] for m in self.rm.milestones}
        for s in self.rm.stages:
            self.assertTrue(set(s["requires"]) <= ids, s["id"])

    def test_stages_are_cumulative(self):
        sizes = [len(self.rm.stage_issue_ids(s)) for s in self.rm.stages]
        self.assertEqual(sizes, sorted(sizes))

    def test_every_issue_has_a_first_stage_or_is_optional(self):
        for i in self.rm.issues:
            if i["milestone"] != "L":
                self.assertIsNotNone(i["stage"], i["id"])

    def test_payload_is_json_serializable_and_docs_resolve(self):
        import json

        payload = vr.build_payload(self.rm)
        json.dumps(payload)
        self.assertGreaterEqual(len(payload["docs"]), 5)
        for d in payload["docs"]:
            self.assertNotIn("<span>", d["html"].replace("<span></span>", ""), f"unresolved link in {d['id']}")


if __name__ == "__main__":
    unittest.main()
