"""Dura Live Line copy must not point users at ibetin.com after the Dura rebrand."""
import re
import unittest
from pathlib import Path

import dura_brand_bootstrap

ROOT = Path(__file__).resolve().parent


def _dura_rendered_source(name: str) -> str:
    text = (ROOT / name).read_text(encoding="utf-8")
    for pattern, replacement in dura_brand_bootstrap.replacements():
        text = pattern.sub(replacement, text)
    return text


class DuraLiveLineBrandingTest(unittest.TestCase):
    def test_liveline_ui_has_no_ibetin_domain_after_rebrand(self):
        text = _dura_rendered_source("ibetin_liveline_v30_unified_ui.py")
        self.assertNotIn("ibetin.com", text.lower())
        self.assertIn("More live markets on durabet.com", text)
        self.assertIn("Continue to durabet.com", text)
        self.assertIn("https://www.durabet.com/live/cricket?", text)

    def test_dotcom_brand_marks_read_durabet(self):
        text = _dura_rendered_source("ibetin_liveline_v30_unified_ui.py")
        self.assertIsNone(re.search(r"DURA<span[^>]*>\.COM", text))
        self.assertIn('DURABET<span>.COM</span>', text)


if __name__ == "__main__":
    unittest.main()
