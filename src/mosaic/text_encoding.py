"""Text decoding helpers for Windows subprocess output."""

from __future__ import annotations

import locale


def decode_process_output(data: bytes) -> str:
    """Decode subprocess output without mojibake on Chinese Windows."""
    encodings = [
        "utf-8-sig",
        "utf-8",
        locale.getpreferredencoding(False),
        "gb18030",
        "cp936",
    ]
    seen: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

