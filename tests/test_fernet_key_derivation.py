"""P0-14 Fernet key PBKDF2 passphrase derivation — v0.3 sprint 5."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent import integrations  # noqa: E402
from agent.integrations import (  # noqa: E402
    PBKDF2_ITERATIONS,
    SALT_BYTES,
    _derive_key_from_passphrase,
)


def _clean_env(env: dict | None = None) -> dict:
    """FERNET_* 환경변수를 비우고 주어진 값으로 덮어쓴 dict 반환."""
    base = {k: v for k, v in os.environ.items() if not k.startswith("TOMORROW_YOU_FERNET_")}
    if env:
        base.update(env)
    return base


class TestDeriveKeyFromPassphrase(unittest.TestCase):
    def test_deterministic_same_input(self):
        salt = b"\x00" * SALT_BYTES
        k1 = _derive_key_from_passphrase("hunter2", salt)
        k2 = _derive_key_from_passphrase("hunter2", salt)
        self.assertEqual(k1, k2)

    def test_different_passphrase_yields_different_key(self):
        salt = b"\x00" * SALT_BYTES
        k1 = _derive_key_from_passphrase("hunter2", salt)
        k2 = _derive_key_from_passphrase("HUNTER2", salt)
        self.assertNotEqual(k1, k2)

    def test_different_salt_yields_different_key(self):
        k1 = _derive_key_from_passphrase("hunter2", b"\x00" * SALT_BYTES)
        k2 = _derive_key_from_passphrase("hunter2", b"\xff" * SALT_BYTES)
        self.assertNotEqual(k1, k2)

    def test_iter_count_baseline(self):
        # OWASP 2023 minimum baseline check — regression guard
        self.assertGreaterEqual(PBKDF2_ITERATIONS, 200_000)

    def test_fernet_accepts_derived_key(self):
        """Fernet은 정확히 32-byte urlsafe-b64 키를 요구 — round-trip 가능 검증."""
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            self.skipTest("cryptography unavailable")
        salt = b"\xab" * SALT_BYTES
        key = _derive_key_from_passphrase("p@ss", salt)
        token = Fernet(key).encrypt(b"hello")
        self.assertEqual(Fernet(key).decrypt(token), b"hello")


class TestLoadKeyPriority(unittest.TestCase):
    """우선순위: FERNET_KEY > PASSPHRASE+salt > KEY_FILE > new random."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._patch = patch.object(integrations, "_KEY_DIR", Path(self._tmp))
        self._patch.start()
        self._patch2 = patch.object(
            integrations, "_KEY_FILE", Path(self._tmp) / "fernet.key"
        )
        self._patch2.start()
        self._patch3 = patch.object(
            integrations, "_SALT_FILE", Path(self._tmp) / "fernet.salt"
        )
        self._patch3.start()

    def tearDown(self):
        self._patch.stop()
        self._patch2.stop()
        self._patch3.stop()

    def test_explicit_env_key_wins_over_passphrase(self):
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            self.skipTest("cryptography unavailable")
        raw = Fernet.generate_key().decode()
        env = {
            "TOMORROW_YOU_FERNET_KEY": raw,
            "TOMORROW_YOU_FERNET_PASSPHRASE": "should-be-ignored",
        }
        with patch.dict(os.environ, _clean_env(env), clear=True):
            key = integrations._load_or_create_key()
        self.assertEqual(key, raw.encode())
        self.assertFalse((Path(self._tmp) / "fernet.salt").exists(),
                         "passphrase 경로는 호출되지 않아야 함 — salt 파일 없어야")

    def test_passphrase_creates_salt_and_derives(self):
        env = {"TOMORROW_YOU_FERNET_PASSPHRASE": "secure-pass-1"}
        with patch.dict(os.environ, _clean_env(env), clear=True):
            key1 = integrations._load_or_create_key()
            salt_path = Path(self._tmp) / "fernet.salt"
            self.assertTrue(salt_path.exists())
            self.assertEqual(len(salt_path.read_bytes()), SALT_BYTES)
            # 같은 passphrase + 같은 salt → 같은 키
            key2 = integrations._load_or_create_key()
            self.assertEqual(key1, key2)

    def test_passphrase_path_does_not_write_key_file(self):
        """passphrase 사용 시 평문 키가 디스크에 남지 않아야 함 — P0-14 핵심."""
        env = {"TOMORROW_YOU_FERNET_PASSPHRASE": "secure-pass-2"}
        with patch.dict(os.environ, _clean_env(env), clear=True):
            integrations._load_or_create_key()
        self.assertFalse((Path(self._tmp) / "fernet.key").exists())

    def test_no_env_falls_back_to_random_key_file(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            k1 = integrations._load_or_create_key()
            self.assertTrue((Path(self._tmp) / "fernet.key").exists())
            k2 = integrations._load_or_create_key()
            self.assertEqual(k1, k2)  # 파일에서 다시 읽어 같은 키


if __name__ == "__main__":
    unittest.main()
