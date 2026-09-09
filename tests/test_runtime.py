"""Offline end-to-end contracts: real parser, durable store, jobs, API and exports."""
import concurrent.futures
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from bs4 import BeautifulSoup
from storage import Store
from job_manager import JobManager
from gta_weekly_scraper import extract_week_range_from_text, gta_week_from_publish_snap, parse_weekly_soup
import history_store
import config
import scan_pipeline
import vehicle_intelligence
import app as api_module
from network import validate_url, fetch_context, get_soup

ARTICLE = """<html><head><meta property="article:published_time" content="2026-09-03T10:00:00Z"></head>
<body><article><h1>GTA Online Weekly Update September 3-9, 2026</h1>
<h2>Podium Vehicle</h2><p>Grotti Turismo Omaggio</p>
<h2>Bonuses</h2><ul><li>3x GTA$ and RP on Community Series</li></ul>
<h2>Discounts</h2><ul><li>Grotti Itali GTO - 40% off</li></ul></article></body></html>"""
SOURCE = "https://example.com/weekly"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(url="", path=Path(self.temp.name) / "state.sqlite3")
        self.deliveries = []
        self.manager = JobManager(storage=self.store, dispatch=lambda job, version: self.deliveries.append((job, version)))
        for module in (api_module, history_store, config, scan_pipeline, vehicle_intelligence):
            if hasattr(module, "store"):
                p = patch.object(module, "store", self.store)
                p.start(); self.addCleanup(p.stop)
        p = patch.object(api_module, "manager", self.manager)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(api_module, "password", "")
        p.start(); self.addCleanup(p.stop)
        p = patch.object(history_store, "HISTORY_DIR", Path(self.temp.name) / "legacy-history")
        p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {"VERCEL": "0", "GTA_CLOUD": "0", "SMTP_USERNAME": "", "SMTP_PASSWORD": "", "EMAIL_TO": ""})
        p.start(); self.addCleanup(p.stop)
        api_module.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = api_module.app.test_client()
        self.params = {"manual_url": SOURCE, "output_dir": self.temp.name, "generate_pdf": True, "save_json": True}

    def drain(self):
        steps = 0
        while self.deliveries:
            job_id, version = self.deliveries.pop(0)
            self.manager.execute(job_id, version)
            steps += 1
            self.assertLess(steps, 100)

    def test_corrections_persist_and_exports_use_revision(self):
        job = self.scan()
        row = job.data['result']['items'][0]
        edit = {key: row.get(key, '') for key in ('item', 'details', 'category')}
        edit.update(index=0, details='Owner correction <safe>')
        response = self.client.put(f'/api/history/{job.id}', json={'revision': 0, 'edits': [edit], 'note': 'Correct reward'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['revision'], 1)
        self.assertFalse(response.json['items'][0]['verified'])
        self.assertIn('original', response.json['items'][0])
        self.assertEqual(self.client.get(f'/api/runs/{job.id}/json').json['revision'], 1)
        self.assertTrue(self.client.get(f'/api/history/{job.id}/pdf').data.startswith(b'%PDF'))
        self.assertEqual(self.client.put(f'/api/history/{job.id}', json={'revision': 0, 'edits': []}).status_code, 400)

    def test_saved_report_email_is_idempotent(self):
        job = self.scan()
        with patch.dict(os.environ, {'SMTP_USERNAME': 'owner@example.com', 'SMTP_PASSWORD': 'test-only'}), patch.object(api_module, 'send_email_with_attachment') as send:
            payload = {'recipients': ['recipient@example.com'], 'requestId': 'unique-delivery-test-123'}
            for _ in range(2):
                response = self.client.post(f'/api/history/{job.id}/email', json=payload)
                self.assertEqual(response.status_code, 200)
            self.assertEqual(send.call_count, 1)
            self.assertEqual(self.client.post(f'/api/history/{job.id}/email', json={**payload, 'recipients': ['a@b\nBcc:c@d']}).status_code, 400)

    def test_configured_sources_include_additional_url(self):
        params = {**self.params, 'source_urls': ['https://example.com/listing']}
        state = {}
        with patch.object(scan_pipeline, 'resolve_source', side_effect=lambda url: (url, 'Weekly article')):
            state, _ = scan_pipeline.advance('test', state, params, lambda *a: None, lambda: False)
            state, _ = scan_pipeline.advance('test', state, params, lambda *a: None, lambda: False)
        self.assertEqual(state['phase'], 'extract')
        self.assertEqual(len(state['sources']), 2)

    def scan(self):
        soup = BeautifulSoup(ARTICLE, "html.parser")
        rows = parse_weekly_soup(soup, SOURCE)
        week = extract_week_range_from_text(soup)
        with patch.object(scan_pipeline, "parse_weekly_generic", return_value=rows), \
             patch.object(scan_pipeline, "_week_for_url", return_value=week), \
             patch.object(scan_pipeline, "collect_article_images", return_value=[]), \
             patch.object(scan_pipeline, "enrich_vehicles", return_value=[{"name": "Grotti Turismo Omaggio", "confidence": .7}]):
            job = self.manager.create(self.params)
            self.drain()
        return self.manager.get(job.id)

    def test_full_pipeline_history_query_and_downloads(self):
        job = self.scan()
        self.assertEqual(job.data["status"], "completed", job.data["error"])
        result = job.data["result"]
        self.assertEqual(result["week_start"], "2026-09-03")
        self.assertGreater(result["row_count"], 1)
        self.assertTrue(Path(result["pdf_path"]).read_bytes().startswith(b"%PDF"))
        self.assertEqual(json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))["id"], job.id)
        self.assertEqual(self.client.get("/api/history").json["history"][0]["id"], job.id)
        self.assertEqual(self.client.get("/api/latest").json["id"], job.id)
        self.assertEqual(self.client.get(f"/api/history/{job.id}/json").json["id"], job.id)
        pdf = self.client.get(f"/api/history/{job.id}/pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        answer = self.client.post("/api/knowledge/query", json={"query": "podium vehicle", "snapshotId": job.id})
        self.assertIn("Turismo", answer.json["answer"])
        # A fresh store/manager sees the exact same report, without process memory.
        restarted = JobManager(storage=Store(url="", path=self.store.path), dispatch=lambda *_: None)
        self.assertEqual(restarted.get(job.id).data["result"]["id"], job.id)
        self.assertNotIn("_params", self.client.get(f"/api/runs/{job.id}").json)

    def test_duplicate_delivery_and_restart_resume_once(self):
        calls = []
        def step(job_id, state, params, progress, cancel):
            calls.append(state.get("step", 0))
            progress("extract", 30, "Checkpoint")
            return {"step": 1}, None if not state else {"id": job_id, "ok": True}
        self.manager.advance = step
        job = self.manager.create(self.params)
        self.deliveries.clear()
        self.manager.execute(job.id, 0)
        restarted = JobManager(storage=Store(url="", path=self.store.path), dispatch=lambda *_: None, advance=step)
        restarted.execute(job.id, 0)  # Stale delivery must not re-execute step zero.
        restarted.execute(job.id, 1)
        restarted.execute(job.id, 1)
        self.assertEqual(calls, [0, 1])
        self.assertEqual(restarted.get(job.id).data["status"], "completed")

    def test_cancel_before_execution(self):
        self.manager.advance = lambda *_: self.fail("Cancelled work must not execute")
        job = self.manager.create(self.params)
        self.assertEqual(self.client.post(f"/api/runs/{job.id}/cancel").status_code, 200)
        self.drain()
        self.assertEqual(self.manager.get(job.id).data["status"], "cancelled")

    def test_atomic_store_parallel_writes(self):
        def increment(_):
            other = Store(url="", path=self.store.path)
            for _ in range(10):
                other.mutate("counter", "value", lambda n: n + 1, default=0)
        self.store.put("counter", "value", 0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(4)))
        self.assertEqual(self.store.get("counter", "value"), 40)

    def test_validation_and_authentication(self):
        self.assertEqual(self.client.post("/api/runs", json=[]).status_code, 400)
        self.assertEqual(self.client.post("/api/runs", json={"generatePdf": "yes"}).status_code, 400)
        self.assertEqual(self.client.put("/api/settings", json={"request_timeout": 999}).status_code, 400)
        self.assertEqual(self.client.put("/api/settings", json={"generate_pdf": "false"}).status_code, 400)
        self.assertEqual(self.client.post("/api/knowledge/query", json={"query": ""}).status_code, 400)
        self.assertEqual(self.client.post("/api/runs", json={"sendEmail": True}).status_code, 400)
        with patch.object(api_module, "password", "a-test-password-only"):
            self.assertEqual(self.client.get("/api/history").status_code, 401)
            self.assertEqual(self.client.get("/api/session").json["authenticated"], False)
            self.assertEqual(self.client.post("/api/session", json={"password": "bad"}).status_code, 401)
            self.assertEqual(self.client.post("/api/session", json={"password": "a-test-password-only"}, headers={"Origin": "https://evil.example"}).status_code, 403)
            self.assertEqual(self.client.post("/api/session", json={"password": "a-test-password-only"}).status_code, 200)
            self.assertEqual(self.client.get("/api/history").status_code, 200)
            self.client.delete("/api/session")
            self.assertEqual(self.client.get("/api/history").status_code, 401)

    def test_cloud_rejects_incomplete_setup(self):
        with patch.dict(os.environ, {"GTA_CLOUD": "1"}):
            self.assertEqual(self.client.get("/api/health").status_code, 503)
            self.assertEqual(self.client.get("/api/session").status_code, 503)

    def test_sse_resume_cursor_and_terminal(self):
        job = self.scan()
        response = self.client.get(f"/api/runs/{job.id}/events", headers={"Last-Event-ID": "999"})
        self.assertIn(b"event: done", response.data)
        self.assertNotIn(b"event: progress", response.data)
        self.assertEqual(self.client.get(f"/api/runs/{job.id}/events?after=no").status_code, 400)

    def test_disabled_exports_remain_disabled(self):
        self.params.update(generate_pdf=False, save_json=False)
        job = self.scan()
        self.assertEqual(self.client.get(f"/api/history/{job.id}/pdf").status_code, 404)
        self.assertEqual(self.client.get(f"/api/history/{job.id}/json").status_code, 404)

    def test_email_secret_not_persisted_and_delivery_not_repeated(self):
        self.params.update(send_email=True, email_config={"username": "sender@example.com", "password": "never-save-this", "to_addrs": ["recipient@example.com"]})
        with patch.object(scan_pipeline, "send_email_with_attachment") as send:
            job = self.scan()
            self.assertEqual(send.call_count, 1)
            self.manager.execute(job.id, 0)
            self.assertEqual(send.call_count, 1)
        self.assertNotIn("never-save-this", self.store.path.read_bytes().decode(errors="ignore"))
        self.assertTrue(job.data["result"]["email_sent"])

    def test_pdf_escapes_source_text(self):
        from intelligence_engine import _write_pdf
        data = {"week_start": "2026-09-03", "week_end": "2026-09-09", "overall_confidence": .7, "sections": {"A & B": [{"item": "<Untrusted>", "details": "A & B > C"}]}, "sources": [], "warnings": ["A < B & C"]}
        self.assertTrue(Path(_write_pdf(data, self.temp.name)).read_bytes().startswith(b"%PDF"))


class DateAndNetworkTests(unittest.TestCase):
    def test_card_parser_uses_item_name_not_price(self):
        html = '<article><h2>Discounts</h2><ul><li class="gta-bonuses"><div class="item-info"><h3><a href="/vehicles/cyclone-ii">Cyclone II</a></h3><s>$2,250,000</s><div class="discounted-price">-70% $675,000</div></div></li></ul></article>'
        rows = parse_weekly_soup(BeautifulSoup(html, "html.parser"), SOURCE)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item"], "Cyclone II")
        self.assertEqual(rows[0]["entity_type"], "vehicle")
        self.assertIn("-70%", rows[0]["details"])

    def test_nested_prize_list_and_article_boundary(self):
        html = '<article><h2>Prize Ride</h2><ul><li>Place Top 2 in a race.<ul><li>Prize: Karin Woodlander</li></ul></li></ul></article><footer><p>Do not extract footer</p></footer>'
        rows = parse_weekly_soup(BeautifulSoup(html, "html.parser"), SOURCE)
        self.assertTrue(any(row["item"] == "Karin Woodlander" and row["category"] == "Prize Ride" for row in rows))
        self.assertFalse(any("footer" in row["item"] for row in rows))

    def test_prices_are_not_vehicles(self):
        from vehicle_intelligence import looks_like_vehicle, load_catalog, _best_catalog_match
        self.assertFalse(looks_like_vehicle("Discounts", "$900,000", load_catalog()))
        self.assertFalse(looks_like_vehicle("Prize Ride", "LS Car Meet Prize Ride", load_catalog()))
        self.assertIsNone(_best_catalog_match("", load_catalog())[0])

    def test_manufacturer_names_merge_without_collapsing_models(self):
        from intelligence_engine import _merge_rows
        a = {"url": "https://a", "provider": "A", "label": "A"}
        b = {"url": "https://b", "provider": "B", "label": "B"}
        rows = _merge_rows([(a, [{"category": "Podium Vehicle", "item": "Declasse Impaler SZ"}]), (b, [{"category": "Podium Vehicle", "item": "Impaler SZ"}])])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["verified"])

    def test_week_ranges_cross_month_and_year(self):
        for title, start, end in [
            ("August 27 - September 2, 2026", "2026-08-27", "2026-09-02"),
            ("September 3rd to 9th, 2026", "2026-09-03", "2026-09-09"),
            ("3-9 September 2026", "2026-09-03", "2026-09-09"),
            ("December 31 - January 6, 2027", "2026-12-31", "2027-01-06"),
        ]:
            with self.subTest(title=title):
                week = extract_week_range_from_text(BeautifulSoup(f"<article><h1>{title}</h1></article>", "html.parser"))
                self.assertIsNotNone(week)
                self.assertEqual(tuple(d.date().isoformat() for d in week), (start, end))

    def test_friday_is_in_current_week_wednesday_announces_next(self):
        zone = ZoneInfo("Asia/Kuwait")
        self.assertEqual(gta_week_from_publish_snap(datetime(2026, 9, 4, tzinfo=zone))[0].day, 3)
        self.assertEqual(gta_week_from_publish_snap(datetime(2026, 9, 2, tzinfo=zone))[0].day, 3)

    def test_private_urls_and_credentials_rejected(self):
        for url in ["file:///etc/passwd", "http://user:password@example.com", "http://127.0.0.1", "http://[::1]", "http://169.254.169.254", "https://example.com:22"]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_cancel_before_network(self):
        with fetch_context(cancel=lambda: True), patch("network.requests.get") as request:
            with self.assertRaises(InterruptedError):
                get_soup(SOURCE)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
