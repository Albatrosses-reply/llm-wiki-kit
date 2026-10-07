"""오프라인 테스트 (네트워크·메일·AI 없음). 실행: .venv/bin/python -m unittest discover -s tests"""
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp()
os.environ["LLM_WIKI_HOME"] = TMP  # 실제 ~/.llm-wiki를 건드리지 않게 (config를 import하기 전에)

from wikikit import config as C  # noqa: E402
from wikikit import curate, ingest, pdfs, scheduler, summarize  # noqa: E402
from wikikit import vault as V  # noqa: E402
from wikikit.collect import Paper, excluded  # noqa: E402
from wikikit.mailer import Mailer  # noqa: E402
from wikikit.store import Store  # noqa: E402


def cfg_for(vault: Path) -> dict:
    cfg = dict(C.DEFAULTS, gmail="me@gmail.com", recipient="me@gmail.com", vault=str(vault))
    cfg["catalog"] = tomllib.loads(C.JOURNALS.read_text(encoding="utf-8"))["groups"]
    cfg["vault_path"] = vault
    return cfg


def paper(i, group="realestate_core", score=0, abstract="We study rents."):
    return Paper(doi=f"10.1/x{i}", title=f"Zoning and rents {i}", authors=["Ann Lee", "Bo Kim", "Cy Park"], journal="Journal of Urban Economics",
                 abbrev="JUE", group=group, pub_date="2026-10-01", abstract=abstract, score=score, item_hash=f"{i:012x}")


class ConfigTests(unittest.TestCase):
    def test_save_roundtrip(self):
        C.save(dict(C.DEFAULTS, gmail='a"b@gmail.com', extra_journals=[{"abbrev": "JRS", "name": 'J "R" S', "issn": ["0022-4146"]}]))
        cfg = C.load()
        self.assertEqual(cfg["gmail"], 'a"b@gmail.com')
        self.assertEqual(cfg["extra_journals"][0]["name"], 'J "R" S')
        self.assertEqual(C.journals(cfg)[-1]["group"], "extra")

    def test_secrets_keep_existing(self):
        C.save_secrets({"GMAIL_APP_PASSWORD": "abcd", "S2_API_KEY": "s2"})
        C.save_secrets({"GMAIL_APP_PASSWORD": "", "ELSEVIER_API_KEY": "el"})
        text = C.SECRETS.read_text(encoding="utf-8")
        self.assertIn("GMAIL_APP_PASSWORD=abcd", text)
        self.assertIn("ELSEVIER_API_KEY=el", text)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.vault = Path(tempfile.mkdtemp())
        V.ensure(self.vault)
        self.cfg = cfg_for(self.vault)

    def test_template_copied_without_keep_files(self):
        self.assertTrue((self.vault / "AGENTS.md").exists())
        self.assertTrue((self.vault / "wiki" / "sources").is_dir())
        self.assertFalse(list(self.vault.rglob(".keep")))

    def test_alerts_scan_and_mark(self):
        ps = [paper(1, score=1), paper(2)]
        f = V.write_alerts(self.vault, "2026-10-07", ps, self.cfg)
        self.assertEqual(V.scan_checked(self.vault), [])
        f.write_text(f.read_text(encoding="utf-8").replace("- [ ] **Zoning and rents 1", "- [x] **Zoning and rents 1"), encoding="utf-8")
        self.assertEqual(V.scan_checked(self.vault), ["000000000001"])
        self.assertEqual(V.mark_checked(self.vault, ["000000000002"]), 1)
        self.assertEqual(len(V.scan_checked(self.vault)), 2)

    def test_citekey(self):
        self.assertEqual(V.make_citekey(["Danny Ben‐Shahar", "A B", "C D"], "2026", set()), "BenshaharEtAl2026")
        self.assertEqual(V.make_citekey(["Ann Lee", "Bo Kim"], "2025", set()), "LeeKim2025")
        self.assertEqual(V.make_citekey(["Lee, Ann"], "2025", {"Lee2025"}), "Lee2025a")
        self.assertEqual(V.make_citekey([], "", set()), "Anonnd")

    def test_poll_creates_candidate(self):
        store = Store(Path(tempfile.mkdtemp()) / "s.db")
        p = paper(3)
        store.add(p)
        self.assertTrue(store.star(p.item_hash, "obsidian"))
        os.environ.pop("GMAIL_APP_PASSWORD", None)
        r = curate.poll(self.cfg, store)
        self.assertEqual(r["new"], 1)
        row = store.row(p.doi)
        self.assertEqual(row["citekey"], "LeeEtAl2026")
        self.assertIn("status: starred", Path(row["note_path"]).read_text(encoding="utf-8"))


class MailTests(unittest.TestCase):
    def test_parse_star(self):
        self.assertEqual(curate.parse_star_message("WIKI-STAR 0123456789ab", "", "WIKI-STAR"), ["0123456789ab"])
        body = "- [x] hash:0123456789ab a\n- [ ] hash:111111111111 b\n- [X] hash:222222222222 c"
        self.assertEqual(curate.parse_star_message("Re: WIKI-STAR BATCH", body, "WIKI-STAR"), ["0123456789ab", "222222222222"])

    def test_render(self):
        cfg = cfg_for(Path(tempfile.mkdtemp()))
        html = Mailer(cfg).render_html([paper(1, score=2), paper(2, group="realestate_ext", abstract="")], "2026-10-07")
        self.assertIn("WIKI-STAR%20000000000001", html)
        self.assertIn("⭐ 관심 키워드 논문 1편", html)
        self.assertIn("초록 미제공", html)
        self.assertIn("부동산 확장", html)


class IngestTests(unittest.TestCase):
    PAGE = """---
type: source
title: wrong title
status: skimmed
---

# t

## ✍️ Contribution (사람)
<!-- human -->
내가 직접 쓴 평가입니다.

## ⚠️ Caveats (사람)
<!-- human -->
<!-- llm-draft: 자동 초안 -->
AI 초안

## 🔬 Research Question
질문

## 🛠️ 연구 방법론
방법

## 📊 주요 결과
결과
"""

    def test_human_sections(self):
        _, body = ingest.split_fm(self.PAGE)
        keep = ingest.human_sections(body)
        self.assertEqual(list(keep), ["## ✍️ Contribution (사람)"])
        new_body = body.replace("내가 직접 쓴 평가입니다.", "<!-- llm-draft -->\nAI가 새로 쓴 초안")
        self.assertIn("내가 직접 쓴 평가입니다.", ingest.restore_human(new_body, keep))
        self.assertNotIn("AI가 새로 쓴 초안", ingest.restore_human(new_body, keep))

    def test_fix_page(self):
        from datetime import date
        p = Path(tempfile.mkdtemp()) / "X.md"
        p.write_text(self.PAGE, encoding="utf-8")
        row = {"citekey": "X", "title": "Right", "authors": "A B | C D", "pub_date": "2026-10-01", "journal": "JUE", "doi": "10.1/x"}
        self.assertTrue(ingest.fix_page(p, row, "초록만", date(2026, 10, 7)))
        meta, _ = ingest.split_fm(p.read_text(encoding="utf-8"))
        self.assertEqual((meta["title"], meta["year"], meta["authors"], meta["read_scope"]), ("Right", 2026, ["A B", "C D"], "초록만"))
        self.assertIn("updated: 2026-10-07", p.read_text(encoding="utf-8"))
        p.write_text("---\ntitle: x\n---\n본문만", encoding="utf-8")
        self.assertFalse(ingest.fix_page(p, row, "초록만", date(2026, 10, 7)))


class MiscTests(unittest.TestCase):
    def test_summary_parse(self):
        out = '설명\n{"aaa": "한국어 요약입니다.", "bbb": "English only"}'
        self.assertEqual(summarize.parse(out), {"aaa": "한국어 요약입니다."})
        self.assertEqual(summarize.parse("no json"), {})

    def test_dois_in_pdf_text(self):
        self.assertEqual(pdfs.dois_in("Real Estate Economics. doi:10.1111/1540-6229.70075)."), {"10.1111/1540-6229.70075"})

    def test_exclude(self):
        self.assertTrue(excluded("Paper title – CORRIGENDUM"))
        self.assertFalse(excluded("Corrections in house prices"))

    def test_mac_plist(self):
        d = scheduler._mac_plist("daily", ["daily"], {"StartCalendarInterval": {"Hour": 5, "Minute": 30}}, "/opt/homebrew/bin")
        self.assertEqual(d["ProgramArguments"][-1], "daily")
        self.assertTrue(d["ProgramArguments"][0].endswith("python"))
        self.assertIn("/opt/homebrew/bin", d["EnvironmentVariables"]["PATH"])


if __name__ == "__main__":
    unittest.main()
