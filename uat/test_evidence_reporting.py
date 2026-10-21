"""Unit checks for traceability semantics and offline artifact integrity, not UAT results.

Run after integration: python3 -m unittest discover -s uat -p 'test_evidence_reporting.py'
"""

import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
# Resolve the local report modules, not the third-party package also named coverage.
spec = importlib.util.spec_from_file_location("coverage", HERE / "coverage.py")
coverage = importlib.util.module_from_spec(spec)
sys.modules["coverage"] = coverage
spec.loader.exec_module(coverage)
spec = importlib.util.spec_from_file_location("offline_html", HERE / "offline_html.py")
offline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline)


class EvidenceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.story = {"id": "ST-UNIT", "cases": ["UNIT-1"], "ac": [{"then": "unit assertion", "cases": ["UNIT-1"]}],
                      "brd": ["HR-UNIT-1"], "blueprint_uat": ["UAT-UNIT-1"],
                      "coverage": {"brd": {"HR-UNIT-1": {"assertion": "full unit behavior", "cases": ["UNIT-1"]}},
                                   "blueprint_uat": {"UAT-UNIT-1": {"assertion": "full unit behavior", "cases": ["UNIT-1"]}}}}
        self.row = {"id": "UNIT-1", "status": "Đạt", "steps": "synthetic unit input", "expected": "unit expected", "actual": "unit actual",
                    "run_at": "2026-01-01", "account": "unit@example.invalid", "shot": "unit.png", "video": "unit.webm", "time": "00:01"}
        self.brd = {"requirement_id": "HR-UNIT-1", "original_priority": "P0", "domain": "GOV", "source_text_verbatim": "synthetic unit requirement"}
        self.uat = {"test_id": "UAT-UNIT-1", "domain": "GOV", "scenario": "unit scenario", "acceptance_assertion": "unit assertion", "requirement_links": "HR-UNIT-1"}

    def compute(self, results=None, stories=None, **kwargs):
        with patch.object(coverage, "read_csv", side_effect=lambda name: [self.brd] if name.startswith("brd") else [self.uat]):
            return coverage.compute([self.row] if results is None else results, [{"module": "unit", "stories": [self.story] if stories is None else stories}], **kwargs)

    def test_explicit_behavior_and_all_ac_are_required(self):
        self.assertEqual(self.compute()["brd"][0]["status"], coverage.PASSED)
        self.story.pop("coverage")
        self.assertEqual(self.compute()["brd"][0]["status"], coverage.PARTIAL)

    def test_one_pass_cannot_hide_failed_obligation(self):
        other = copy.deepcopy(self.story)
        other["id"] = "ST-UNIT-OTHER"
        other["cases"] = ["UNIT-MISSING"]
        self.assertEqual(self.compute(stories=[self.story, other])["brd"][0]["status"], coverage.PARTIAL)

    def test_duplicate_results_never_select_the_pass(self):
        failed = dict(self.row, status="Không đạt")
        result = self.compute(results=[failed, self.row])
        self.assertNotEqual(result["brd"][0]["status"], coverage.PASSED)
        self.assertTrue(result["errors"])

    def test_missing_files_and_missing_case_remain_visible(self):
        with tempfile.TemporaryDirectory() as root:
            result = self.compute(evidence_root=root, videos=[{"file": "unit.webm"}])
            self.assertIn("thiếu tệp ảnh", result["case_issues"]["UNIT-1"])
            self.assertEqual(result["brd"][0]["status"], coverage.PARTIAL)
        self.assertEqual(self.compute(results=[])["missing_cases"], ["UNIT-1"])

    def test_module_without_stories_is_not_coverage(self):
        self.assertEqual(self.compute(stories=[])["brd"][0]["status"], "Chưa có story")

    def test_catalogue_shortfall_is_not_complete(self):
        result = self.compute()
        self.assertFalse(result["catalog_complete"])
        self.assertEqual(sum(d["total"] for d in result["domains"]), 1)
        self.assertEqual(len(result["domains"]), 17)

    def test_local_media_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(coverage.local_media(root, "../outside.png"))

    def test_artifact_checks_external_and_broken_anchors(self):
        parser = offline.ArtifactParser()
        parser.feed("<a href='#absent'>case</a><img src='https://example.invalid/unit.png'><div id='same'></div><div id='same'></div>")
        self.assertIn("absent", parser.refs)
        self.assertTrue(any("Non-self-contained" in issue for issue in parser.errors))
        self.assertTrue(any("Duplicate anchor" in issue for issue in parser.errors))

    def test_media_content_is_validated_not_just_data_uri(self):
        parser = offline.ArtifactParser()
        parser.feed("<video src='data:video/mp4;base64,bm90LXZpZGVv'></video>")
        self.assertTrue(parser.errors)
        self.assertEqual(parser.videos, 0)


if __name__ == "__main__":
    unittest.main()
