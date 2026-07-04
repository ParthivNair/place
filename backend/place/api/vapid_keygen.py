"""Generate a VAPID keypair in .env format.

Usage:
    python -m place.api.vapid_keygen [--subject mailto:you@example.com]

Prints VAPID_PRIVATE_KEY / VAPID_PUBLIC_KEY / VAPID_SUBJECT lines ready to
paste into the repo-root .env. Keys are raw base64url (the format pywebpush
accepts and the browser's applicationServerKey expects).
"""

from __future__ import annotations

import argparse
import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_env_lines(subject: str = "mailto:admin@example.com") -> list[str]:
    vapid = Vapid()
    vapid.generate_keys()
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return [
        f"VAPID_PRIVATE_KEY={_b64url(private_raw)}",
        f"VAPID_PUBLIC_KEY={_b64url(public_raw)}",
        f"VAPID_SUBJECT={subject}",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject",
        default="mailto:admin@example.com",
        help="VAPID subject (mailto: or https: URI identifying the sender)",
    )
    args = parser.parse_args()
    for line in generate_env_lines(args.subject):
        print(line)


if __name__ == "__main__":
    main()
