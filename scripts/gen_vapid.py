#!/usr/bin/env python3
"""Wave 6: VAPID 키 생성기.

OSS 정렬 — cryptography(이미 P0-14에서 의존성) ec P-256으로 키 쌍 생성.
"""

from __future__ import annotations

import base64
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> int:
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_bytes = priv.private_numbers().private_value.to_bytes(32, "big")
    pub_point = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    private_b64 = _b64url(priv_bytes)
    public_b64 = _b64url(pub_point)
    print("# Add these to backend environment (e.g., systemd EnvironmentFile or .env):")
    print(f"NAEIL_VAPID_PUBLIC_KEY={public_b64}")
    print(f"NAEIL_VAPID_PRIVATE_KEY={private_b64}")
    print("NAEIL_VAPID_SUBJECT=mailto:admin@example.com")
    print()
    print("# Also expose the public key to the frontend (Next.js public env):")
    print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={public_b64}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
