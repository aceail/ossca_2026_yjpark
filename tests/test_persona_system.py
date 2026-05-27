"""G011 PersonaSystem — Builder audit + 5 default seed + save_persona."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona, list_personas  # noqa: E402
from persona import (  # noqa: E402
    BUILTIN_PERSONAS,
    FORBIDDEN_GROUPS,
    audit_custom_persona,
    save_persona,
    seed_builtin_prompts,
)


class TestForbiddenAudit(unittest.TestCase):
    def test_clean_payload_accepted(self):
        result = audit_custom_persona({
            "name": "내 옛 친구 ㅇㅇ",
            "perspective": "2nd",
            "tone_mode": "Witty",
            "voice_style": "능청맞은 친구 톤",
            "greeting": "야 오랜만이다",
            "system_prompt_override": "2인칭 친구 톤. 짧고 가벼움.",
        })
        self.assertTrue(result.accepted)
        self.assertEqual(result.violations, [])

    def test_gaslighting_word_in_name_rejected(self):
        result = audit_custom_persona({"name": "내 게으름의 친구", "voice_style": "x", "greeting": "x"})
        self.assertFalse(result.accepted)
        self.assertTrue(any(v[1] == "한국 가스라이팅" for v in result.violations))

    def test_identity_failure_in_voice_rejected(self):
        result = audit_custom_persona({"name": "x", "voice_style": "도태된 자 톤", "greeting": "x"})
        self.assertFalse(result.accepted)
        self.assertTrue(any(v[2] == "도태" for v in result.violations))

    def test_korean_trigger_in_system_prompt_rejected(self):
        result = audit_custom_persona({
            "name": "x", "voice_style": "y", "greeting": "z",
            "system_prompt_override": "부모 기대를 자주 언급하라",
        })
        self.assertFalse(result.accepted)
        self.assertTrue(any(v[2] == "부모 기대" for v in result.violations))

    def test_swearword_in_greeting_rejected(self):
        result = audit_custom_persona({"name": "x", "voice_style": "y", "greeting": "야 씨발"})
        self.assertFalse(result.accepted)
        self.assertTrue(any(v[2] == "씨발" for v in result.violations))


class TestBuiltinPersonas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_builtin_count(self):
        self.assertEqual(len(BUILTIN_PERSONAS), 6)

    def test_perspective_variety(self):
        perspectives = {p.perspective for p in BUILTIN_PERSONAS}
        self.assertEqual(perspectives, {"1st", "2nd", "3rd"})

    def test_tone_variety(self):
        tones = {p.tone_mode for p in BUILTIN_PERSONAS}
        self.assertTrue(tones.issubset({"Quiet", "Sharp", "Witty", "Savage"}))

    def test_seed_fills_system_prompts(self):
        updated = seed_builtin_prompts(self.conn)
        self.assertEqual(updated, 6)
        morning = get_persona(self.conn, "내일의 나")
        self.assertIsNotNone(morning["system_prompt_override"])
        self.assertIn("1인칭", morning["system_prompt_override"])

    def test_seed_idempotent(self):
        seed_builtin_prompts(self.conn)
        updated2 = seed_builtin_prompts(self.conn)
        self.assertEqual(updated2, 0, "second seed should update 0 rows")

    def test_builtin_user_facing_fields_pass_audit(self):
        # builtin의 system_prompt_override는 절대 금지어 리스트를 negative prompt로 포함하므로
        # audit 면제. 사용자 노출 필드(name·voice_style·greeting)만 audit 통과해야 함.
        for spec in BUILTIN_PERSONAS:
            result = audit_custom_persona({
                "name": spec.name,
                "voice_style": spec.voice_style,
                "greeting": spec.greeting,
            })
            self.assertTrue(result.accepted,
                            f"builtin persona '{spec.name}' user-facing fields violated audit: {result.violations}")


class TestSavePersona(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        self.conn.execute("INSERT INTO User (id, created_at) VALUES (?, datetime('now'))", ("local-test",))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_save_custom_persona(self):
        payload = {
            "name": "내 옛 동기",
            "perspective": "2nd",
            "tone_mode": "Witty",
            "voice_style": "능청맞은 친구 톤",
            "greeting": "야 오랜만",
            "forbidden_topics": ["전 직장"],
            "system_prompt_override": "2인칭 친구 톤. 짧고 가벼움.",
            "avatar_color": "#888888",
            "avatar_icon": "👥",
        }
        result = audit_custom_persona(payload)
        self.assertTrue(result.accepted)
        pid = save_persona(self.conn, result.sanitized, is_builtin=False, user_id="local-test")
        self.conn.commit()
        row = self.conn.execute("SELECT name, tone_mode, is_builtin FROM Persona WHERE id = ?", (pid,)).fetchone()
        self.assertEqual(row["name"], "내 옛 동기")
        self.assertEqual(row["tone_mode"], "Witty")
        self.assertEqual(row["is_builtin"], 0)

    def test_builtin_seed_via_migration_present(self):
        # 001_initial.sql 5 default INSERT + 006_add_savage_persona.sql 1 INSERT = 6
        builtins = list_personas(self.conn, builtin_only=True)
        self.assertEqual(len(builtins), 6)


if __name__ == "__main__":
    unittest.main()
