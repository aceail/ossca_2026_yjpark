"""tests/test_agent_tools.py — G010 AgentIntegrations 단위 테스트.

커버리지:
  - ToolRouter 키워드 매핑 (5+ 테스트)
  - ExternalIntegration encrypt/decrypt 라운드트립 (3+ 테스트)
  - 각 tool mock 결과 검증 (3+ 테스트)
  - ToolInvocation 로그 검증 (2+ 테스트)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db, migrate
from agent.integrations import save_integration, get_integration, revoke_integration
from agent.router import ToolRouter
from agent.tools.google_calendar import GoogleCalendarTool
from agent.tools.local_files import LocalFilesTool
from agent.tools.web_search import WebSearchTool


def _make_db():
    """테스트용 인메모리 DB (마이그레이션 적용)."""
    conn = open_db(":memory:")
    migrate(conn)
    return conn


def _insert_user(conn, user_id: str = "test-user-001") -> str:
    from datetime import datetime, timezone
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at) VALUES (?, ?)",
        (user_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return user_id


# ────────────────────────────────────────────────────────────────────
# ToolRouter 키워드 매핑 테스트
# ────────────────────────────────────────────────────────────────────

class TestToolRouter(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        _insert_user(self.conn)
        self.router = ToolRouter(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_deadline_keyword_maps_to_calendar(self):
        """'마감' 키워드 → google_calendar.list_events."""
        tools = self.router.route("오늘 마감인 과제가 있어", user_profile=None)
        tool_names = [t.name for t in tools]
        self.assertIn("google_calendar.list_events", tool_names)

    def test_ppt_keyword_maps_to_local_files(self):
        """'PPT' 키워드 → local_files.recent."""
        tools = self.router.route("PPT 발표 준비해야 하는데", user_profile=None)
        tool_names = [t.name for t in tools]
        self.assertIn("local_files.recent", tool_names)

    def test_search_keyword_maps_to_web_search(self):
        """'참고' 키워드 → web_search.brave."""
        tools = self.router.route("참고할 자료 좀 찾아줘", user_profile=None)
        tool_names = [t.name for t in tools]
        self.assertIn("web_search.brave", tool_names)

    def test_multiple_keywords_returns_multiple_tools(self):
        """'마감 + 파일' 키워드 → calendar + files 둘 다."""
        tools = self.router.route("내일까지 파일 제출해야 해", user_profile=None)
        tool_names = [t.name for t in tools]
        self.assertIn("google_calendar.list_events", tool_names)
        self.assertIn("local_files.recent", tool_names)

    def test_empty_input_returns_empty_list(self):
        """빈 입력 → 빈 list."""
        self.assertEqual(self.router.route(""), [])
        self.assertEqual(self.router.route("   "), [])

    def test_no_keyword_match_returns_empty(self):
        """매칭 키워드 없음 → 빈 list."""
        tools = self.router.route("오늘 날씨가 맑네요")
        self.assertEqual(tools, [])

    def test_disabled_tool_not_returned(self):
        """disabled(enabled=0) tool은 반환 안 됨."""
        # google_calendar.event_detail은 enabled=0
        tools = self.router.route("일정 상세 내용 알려줘")
        tool_names = [t.name for t in tools]
        self.assertNotIn("google_calendar.event_detail", tool_names)

    def test_route_returns_agent_tool_objects(self):
        """반환값이 AgentTool 인스턴스."""
        from agent.router import AgentTool
        tools = self.router.route("마감이 언제야")
        for tool in tools:
            self.assertIsInstance(tool, AgentTool)
            self.assertIsNotNone(tool.agent_tool_id)


# ────────────────────────────────────────────────────────────────────
# ExternalIntegration encrypt/decrypt 라운드트립 테스트
# ────────────────────────────────────────────────────────────────────

class TestExternalIntegration(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.user_id = _insert_user(self.conn)
        # 테스트용 키 고정 (환경변수로 주입)
        from cryptography.fernet import Fernet
        test_key = Fernet.generate_key().decode()
        os.environ["TOMORROW_YOU_FERNET_KEY"] = test_key

    def tearDown(self):
        self.conn.close()
        os.environ.pop("TOMORROW_YOU_FERNET_KEY", None)

    def test_save_and_get_roundtrip(self):
        """save → get → 토큰 복호화 검증."""
        save_integration(
            self.conn,
            user_id=self.user_id,
            provider="google_calendar",
            oauth_token="secret-oauth-token-abc123",
            refresh_token="secret-refresh-token-xyz789",
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            expires_at="2026-12-31T00:00:00+00:00",
        )
        result = get_integration(self.conn, self.user_id, "google_calendar")
        self.assertIsNotNone(result)
        self.assertEqual(result["oauth_token"], "secret-oauth-token-abc123")
        self.assertEqual(result["refresh_token"], "secret-refresh-token-xyz789")
        self.assertEqual(result["provider"], "google_calendar")

    def test_fernet_key_auto_generate(self):
        """TOMORROW_YOU_FERNET_KEY 없을 때 자동 생성 키로 암호화/복호화."""
        os.environ.pop("TOMORROW_YOU_FERNET_KEY", None)
        # ~/.tomorrow_you/fernet.key 자동 생성 경로에 의존
        save_integration(
            self.conn,
            user_id=self.user_id,
            provider="local_files",
            oauth_token="auto-key-test-token",
            refresh_token=None,
            scopes=[],
            expires_at=None,
        )
        result = get_integration(self.conn, self.user_id, "local_files")
        self.assertIsNotNone(result)
        self.assertEqual(result["oauth_token"], "auto-key-test-token")

    def test_revoke_removes_integration(self):
        """revoke 후 get_integration → None."""
        save_integration(
            self.conn,
            user_id=self.user_id,
            provider="search",
            oauth_token="search-token",
            refresh_token=None,
            scopes=[],
            expires_at=None,
        )
        self.assertIsNotNone(get_integration(self.conn, self.user_id, "search"))
        revoke_integration(self.conn, self.user_id, "search")
        self.assertIsNone(get_integration(self.conn, self.user_id, "search"))

    def test_upsert_updates_token(self):
        """동일 provider 재저장 시 토큰 갱신."""
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "old-token", None, [], None,
        )
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "new-token", None, [], None,
        )
        result = get_integration(self.conn, self.user_id, "google_calendar")
        self.assertEqual(result["oauth_token"], "new-token")

    def test_token_stored_encrypted(self):
        """DB에 저장된 토큰이 평문이 아님을 검증."""
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "plaintext-secret", None, [], None,
        )
        row = self.conn.execute(
            "SELECT oauth_token_encrypted FROM ExternalIntegration WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        raw = bytes(row["oauth_token_encrypted"])
        self.assertNotEqual(raw, b"plaintext-secret")
        self.assertNotIn(b"plaintext-secret", raw)


# ────────────────────────────────────────────────────────────────────
# 각 tool mock 결과 검증 테스트
# ────────────────────────────────────────────────────────────────────

class TestGoogleCalendarTool(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.user_id = _insert_user(self.conn)
        from cryptography.fernet import Fernet
        os.environ["TOMORROW_YOU_FERNET_KEY"] = Fernet.generate_key().decode()

    def tearDown(self):
        self.conn.close()
        os.environ.pop("TOMORROW_YOU_FERNET_KEY", None)

    def test_no_token_returns_empty(self):
        """토큰 없으면 빈 list."""
        tool = GoogleCalendarTool(self.conn, self.user_id)
        result = tool.list_upcoming_events()
        self.assertEqual(result, [])

    def test_with_token_returns_mock_events(self):
        """토큰 있으면 mock 일정 3개 반환."""
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "mock-oauth-token", None, ["calendar.readonly"], None,
        )
        tool = GoogleCalendarTool(self.conn, self.user_id)
        result = tool.list_upcoming_events(days=7)
        self.assertEqual(len(result), 3)
        for event in result:
            self.assertIn("summary", event)
            self.assertIn("start", event)
            self.assertIn("end", event)

    def test_event_fields_present(self):
        """반환된 이벤트에 필수 필드 포함."""
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "mock-token", None, [], None,
        )
        tool = GoogleCalendarTool(self.conn, self.user_id)
        events = tool.list_upcoming_events()
        self.assertGreater(len(events), 0)
        first = events[0]
        self.assertIn("id", first)
        self.assertIn("summary", first)


class TestLocalFilesTool(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.user_id = _insert_user(self.conn)
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        self.conn.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _create_file(self, name: str, content: str = "test") -> Path:
        p = Path(self.tmpdir) / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_recent_files_finds_new_file(self):
        """최근 생성 파일이 결과에 포함됨."""
        self._create_file("report.docx")
        tool = LocalFilesTool(self.conn, self.user_id, [self.tmpdir])
        result = tool.recent_files(hours=72)
        names = [f["name"] for f in result]
        self.assertIn("report.docx", names)

    def test_ppt_filter(self):
        """'PPT' 키워드 → .pptx 파일만 필터."""
        self._create_file("slide.pptx")
        self._create_file("notes.txt")
        tool = LocalFilesTool(self.conn, self.user_id, [self.tmpdir])
        result = tool.recent_files(category_keyword="PPT", hours=72)
        names = [f["name"] for f in result]
        self.assertIn("slide.pptx", names)
        self.assertNotIn("notes.txt", names)

    def test_nonexistent_dir_returns_empty(self):
        """존재하지 않는 폴더 → 빈 list."""
        tool = LocalFilesTool(self.conn, self.user_id, ["/nonexistent/path/xyz"])
        result = tool.recent_files()
        self.assertEqual(result, [])

    def test_file_dict_fields(self):
        """반환 dict에 필수 필드 포함."""
        self._create_file("test.pdf")
        tool = LocalFilesTool(self.conn, self.user_id, [self.tmpdir])
        result = tool.recent_files(hours=72)
        self.assertGreater(len(result), 0)
        first = result[0]
        for field in ("path", "name", "size_bytes", "modified_at", "extension"):
            self.assertIn(field, first)


class TestWebSearchTool(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.user_id = _insert_user(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_mock_search_returns_3_results(self):
        """mock 검색 → 3건 반환."""
        tool = WebSearchTool(self.conn, self.user_id)
        result = tool.search("미루기 극복 방법")
        self.assertEqual(len(result), 3)

    def test_result_fields_present(self):
        """반환 dict에 필수 필드 포함."""
        tool = WebSearchTool(self.conn, self.user_id)
        result = tool.search("생산성 향상 팁")
        for item in result:
            for field in ("title", "url", "snippet", "rank"):
                self.assertIn(field, item)

    def test_max_results_limit(self):
        """max_results=1 → 1건만 반환."""
        tool = WebSearchTool(self.conn, self.user_id)
        result = tool.search("test query", max_results=1)
        self.assertEqual(len(result), 1)

    def test_query_appears_in_results(self):
        """결과에 쿼리 관련 내용 포함."""
        tool = WebSearchTool(self.conn, self.user_id)
        result = tool.search("OSSCA 프로젝트")
        self.assertGreater(len(result), 0)
        # mock 결과에 쿼리 텍스트가 포함됨
        combined = " ".join(item["title"] + item["snippet"] for item in result)
        self.assertIn("OSSCA 프로젝트", combined)


# ────────────────────────────────────────────────────────────────────
# ToolInvocation 로그 검증 테스트
# ────────────────────────────────────────────────────────────────────

class TestToolInvocationLog(unittest.TestCase):

    def setUp(self):
        self.conn = _make_db()
        self.user_id = _insert_user(self.conn)
        from cryptography.fernet import Fernet
        os.environ["TOMORROW_YOU_FERNET_KEY"] = Fernet.generate_key().decode()

    def tearDown(self):
        self.conn.close()
        os.environ.pop("TOMORROW_YOU_FERNET_KEY", None)

    def _invocation_count(self, user_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM ToolInvocation WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row["cnt"]

    def test_calendar_tool_logs_invocation(self):
        """GoogleCalendarTool 호출 후 ToolInvocation row INSERT 검증."""
        save_integration(
            self.conn, self.user_id, "google_calendar",
            "mock-token", None, [], None,
        )
        before = self._invocation_count(self.user_id)
        tool = GoogleCalendarTool(self.conn, self.user_id)
        tool.list_upcoming_events()
        after = self._invocation_count(self.user_id)
        self.assertEqual(after, before + 1)

    def test_web_search_logs_invocation(self):
        """WebSearchTool 호출 후 ToolInvocation row INSERT 검증."""
        before = self._invocation_count(self.user_id)
        tool = WebSearchTool(self.conn, self.user_id)
        tool.search("테스트 쿼리")
        after = self._invocation_count(self.user_id)
        self.assertEqual(after, before + 1)

    def test_local_files_logs_invocation(self):
        """LocalFilesTool 호출 후 ToolInvocation row INSERT 검증."""
        tmpdir = tempfile.mkdtemp()
        try:
            before = self._invocation_count(self.user_id)
            tool = LocalFilesTool(self.conn, self.user_id, [tmpdir])
            tool.recent_files()
            after = self._invocation_count(self.user_id)
            self.assertEqual(after, before + 1)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_invocation_log_contains_input_output(self):
        """ToolInvocation 로그에 input_json, output_json 저장 검증."""
        tool = WebSearchTool(self.conn, self.user_id)
        tool.search("감사 로그 테스트")

        row = self.conn.execute(
            """
            SELECT ti.input_json, ti.output_json, ti.latency_ms, at.name
            FROM ToolInvocation ti
            JOIN AgentTool at ON at.id = ti.agent_tool_id
            WHERE ti.user_id = ? AND at.name = 'web_search.brave'
            ORDER BY ti.invoked_at DESC LIMIT 1
            """,
            (self.user_id,),
        ).fetchone()

        self.assertIsNotNone(row)
        import json
        input_data = json.loads(row["input_json"])
        self.assertEqual(input_data["query"], "감사 로그 테스트")
        output_data = json.loads(row["output_json"])
        self.assertIn("results", output_data)
        self.assertIsNotNone(row["latency_ms"])

    def test_no_token_calendar_still_logs(self):
        """토큰 없는 경우에도 ToolInvocation 로그 기록됨."""
        before = self._invocation_count(self.user_id)
        tool = GoogleCalendarTool(self.conn, self.user_id)
        result = tool.list_upcoming_events()
        after = self._invocation_count(self.user_id)
        self.assertEqual(result, [])
        self.assertEqual(after, before + 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
