"""Sprint 34 — OnlyOffice WOPI-style endpoints."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# OnlyOffice env BEFORE app import
os.environ["TOMORROW_YOU_OO_JWT_SECRET"] = "test-secret-32bytes-long-please-x"
os.environ["TOMORROW_YOU_OO_PUBLIC_URL"] = "http://localhost:8090"
os.environ["TOMORROW_YOU_BACKEND_INTERNAL_URL"] = "http://backend:8001"
os.environ["TOMORROW_YOU_OO_INTERNAL_URL"] = "http://onlyoffice"

from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH

_TMP_UPLOAD_ROOT = tempfile.mkdtemp(prefix="oo_upload_")
os.environ["TOMORROW_YOU_UPLOAD_ROOT"] = _TMP_UPLOAD_ROOT

from backend.main import app
from backend.deps import get_db
from db import open_db, migrate
from persona import seed_builtin_prompts


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_TMP_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _get_test_db():
    c = _conn()
    try:
        yield c
    finally:
        c.close()


app.dependency_overrides[get_db] = _get_test_db


def setUpModule():
    os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
    app.dependency_overrides[get_db] = _get_test_db
    c = open_db(_TMP_DB_PATH)
    migrate(c)
    seed_builtin_prompts(c)
    c.close()


def tearDownModule():
    try:
        os.unlink(_TMP_DB_PATH)
    except Exception:
        pass


client = TestClient(app, raise_server_exceptions=True)


def _create_user():
    r = client.post("/api/users", json={})
    d = r.json()
    return d["user_id"], {"Authorization": f"Bearer {d['device_token']}"}


def _upload_file(u, h, name, content):
    tid = client.post(
        "/api/tasks", headers=h, json={"user_id": u, "title": "edit-test"}
    ).json()["id"]
    client.post(
        f"/api/tasks/{tid}/upload", headers=h,
        files=[("files", (name, content, "application/octet-stream"))],
    )
    return tid


class TestJWTHelpers(unittest.TestCase):
    def test_sign_and_verify_round_trip(self):
        from backend.api.onlyoffice import _sign_edit_token, _verify_edit_token
        tok = _sign_edit_token(user_id="u1", task_id=42, filename="x.docx")
        claims = _verify_edit_token(tok)
        self.assertEqual(claims["user_id"], "u1")
        self.assertEqual(claims["task_id"], 42)
        self.assertEqual(claims["filename"], "x.docx")
        self.assertEqual(claims["kind"], "edit")

    def test_verify_rejects_tampered(self):
        from backend.api.onlyoffice import _sign_edit_token, _verify_edit_token
        from fastapi import HTTPException
        tok = _sign_edit_token(user_id="u", task_id=1, filename="x.docx") + "x"
        with self.assertRaises(HTTPException) as cm:
            _verify_edit_token(tok)
        self.assertEqual(cm.exception.status_code, 401)


class TestEditConfig(unittest.TestCase):
    def test_returns_config_for_docx(self):
        u, h = _create_user()
        tid = _upload_file(u, h, "report.docx", b"PK\x03\x04fake-docx")
        r = client.get(f"/api/tasks/{tid}/files/report.docx/edit-config", headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["documentServerUrl"], "http://localhost:8090")
        cfg = body["config"]
        self.assertEqual(cfg["document"]["fileType"], "docx")
        self.assertEqual(cfg["documentType"], "word")
        self.assertIn("http://backend:8001/api/_oo/doc?t=", cfg["document"]["url"])
        self.assertIn(
            "http://backend:8001/api/_oo/callback?t=",
            cfg["editorConfig"]["callbackUrl"],
        )
        self.assertTrue(body["token"])  # config JWT

    def test_pptx_is_slide(self):
        u, h = _create_user()
        tid = _upload_file(u, h, "deck.pptx", b"PK\x03\x04fake-pptx")
        r = client.get(f"/api/tasks/{tid}/files/deck.pptx/edit-config", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["config"]["documentType"], "slide")

    def test_document_key_is_safe_charset(self):
        """OnlyOffice key는 [a-zA-Z0-9_-]만 허용 — 한글 파일명이라도."""
        import re
        u, h = _create_user()
        tid = _upload_file(u, h, "발표대본.docx", b"PK\x03\x04fake-docx")
        r = client.get(
            "/api/tasks/{}/files/%EB%B0%9C%ED%91%9C%EB%8C%80%EB%B3%B8.docx/edit-config".format(tid),
            headers=h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        key = r.json()["config"]["document"]["key"]
        self.assertRegex(key, r"^[a-zA-Z0-9_-]{1,128}$")
        # 동일 파일 두 번째 요청은 같은 key (mtime 같으면) — cache 일관성
        r2 = client.get(
            "/api/tasks/{}/files/%EB%B0%9C%ED%91%9C%EB%8C%80%EB%B3%B8.docx/edit-config".format(tid),
            headers=h,
        )
        self.assertEqual(r2.json()["config"]["document"]["key"], key)

    def test_unsupported_ext_400(self):
        u, h = _create_user()
        tid = _upload_file(u, h, "blob.bin", b"\x00\x01\x02")
        r = client.get(f"/api/tasks/{tid}/files/blob.bin/edit-config", headers=h)
        self.assertEqual(r.status_code, 400)

    def test_missing_file_404(self):
        u, h = _create_user()
        tid = client.post(
            "/api/tasks", headers=h, json={"user_id": u, "title": "noupload"}
        ).json()["id"]
        r = client.get(f"/api/tasks/{tid}/files/missing.docx/edit-config", headers=h)
        self.assertEqual(r.status_code, 404)

    def test_owner_required(self):
        u1, h1 = _create_user()
        tid = _upload_file(u1, h1, "secret.docx", b"X")
        u2, h2 = _create_user()
        r = client.get(f"/api/tasks/{tid}/files/secret.docx/edit-config", headers=h2)
        self.assertEqual(r.status_code, 403)


class TestOoDocEndpoint(unittest.TestCase):
    def test_doc_returns_file_with_valid_token(self):
        from backend.api.onlyoffice import _sign_edit_token
        u, h = _create_user()
        tid = _upload_file(u, h, "x.docx", b"the-content")
        tok = _sign_edit_token(user_id=u, task_id=tid, filename="x.docx")
        r = client.get(f"/api/_oo/doc?t={tok}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"the-content")

    def test_doc_rejects_invalid_token(self):
        r = client.get("/api/_oo/doc?t=garbage")
        self.assertEqual(r.status_code, 401)


class TestOoCallbackUrlRewrite(unittest.TestCase):
    """OnlyOffice가 보낸 callback url의 외부 host를 docker internal로 치환."""

    def test_rewrites_localhost_8090_to_onlyoffice(self):
        from backend.api.onlyoffice import _rewrite_oo_callback_url
        u = "http://localhost:8090/cache/files/data/key/output.docx"
        self.assertEqual(
            _rewrite_oo_callback_url(u),
            "http://onlyoffice/cache/files/data/key/output.docx",
        )

    def test_preserves_unrelated_urls(self):
        from backend.api.onlyoffice import _rewrite_oo_callback_url
        u = "http://otherhost:8090/cache/x"
        self.assertEqual(_rewrite_oo_callback_url(u), u)

    def test_handles_exact_public_url(self):
        from backend.api.onlyoffice import _rewrite_oo_callback_url
        self.assertEqual(
            _rewrite_oo_callback_url("http://localhost:8090"),
            "http://onlyoffice",
        )


class TestOoCallback(unittest.TestCase):
    def test_callback_status_1_acks(self):
        from backend.api.onlyoffice import _sign_edit_token
        u, h = _create_user()
        tid = _upload_file(u, h, "x.docx", b"orig")
        tok = _sign_edit_token(user_id=u, task_id=tid, filename="x.docx")
        r = client.post(f"/api/_oo/callback?t={tok}", json={"status": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"error": 0})

    def test_callback_status_2_saves_from_url(self):
        # status=2 (MustSave) — body.url에서 새 컨텐츠 가져와 덮어쓰기
        import http.server
        import threading
        from backend.api.onlyoffice import _sign_edit_token

        u, h = _create_user()
        tid = _upload_file(u, h, "x.docx", b"original")
        tok = _sign_edit_token(user_id=u, task_id=tid, filename="x.docx")

        new_content = b"updated-by-onlyoffice"

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(new_content)))
                self.end_headers()
                self.wfile.write(new_content)

            def log_message(self, *args, **kwargs):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = srv.server_address[1]
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            r = client.post(
                f"/api/_oo/callback?t={tok}",
                json={"status": 2, "url": f"http://127.0.0.1:{port}/x.docx"},
            )
            self.assertEqual(r.status_code, 200)
            # 파일이 새 내용으로 덮어써졌는지 확인
            from backend.api.tasks import _upload_root
            saved = (_upload_root() / u / str(tid) / "x.docx").read_bytes()
            self.assertEqual(saved, new_content)
        finally:
            srv.shutdown()

    def test_callback_rejects_invalid_url_scheme(self):
        from backend.api.onlyoffice import _sign_edit_token
        u, h = _create_user()
        tid = _upload_file(u, h, "x.docx", b"a")
        tok = _sign_edit_token(user_id=u, task_id=tid, filename="x.docx")
        r = client.post(
            f"/api/_oo/callback?t={tok}",
            json={"status": 2, "url": "file:///etc/passwd"},
        )
        # WOPI 약속: HTTP 200 + {"error": 1} (HTTP 4xx/5xx 던지면 OnlyOffice가
        # "system file error"로 사용자에게 표시되어 디버깅 불가)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["error"], 1)
        self.assertIn("scheme", r.json().get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
