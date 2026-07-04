"""VAPID keygen helper emits valid raw-base64url keys in .env format."""

from __future__ import annotations

import base64

from place.api.vapid_keygen import generate_env_lines


def _unb64url(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_env_lines_shape_and_key_material() -> None:
    lines = generate_env_lines(subject="mailto:me@place.test")
    assert lines[0].startswith("VAPID_PRIVATE_KEY=")
    assert lines[1].startswith("VAPID_PUBLIC_KEY=")
    assert lines[2] == "VAPID_SUBJECT=mailto:me@place.test"

    private = _unb64url(lines[0].split("=", 1)[1])
    public = _unb64url(lines[1].split("=", 1)[1])
    assert len(private) == 32  # raw P-256 scalar
    assert len(public) == 65 and public[0] == 0x04  # uncompressed EC point


def test_keys_are_unique_per_invocation() -> None:
    assert generate_env_lines()[0] != generate_env_lines()[0]
