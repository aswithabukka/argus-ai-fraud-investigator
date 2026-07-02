"""PII masking for account identifiers.

PaySim account ids (e.g. C1424948489) stand in for real customer identifiers.
Before any evidence goes to the model we replace them with stable pseudonyms
(ACCT_a1b2c3), preserving relationships (same account -> same token) so the
Analyzer can still reason about "sender == receiver" etc. The mapping is kept
locally and only reversed when writing the final, human-facing case file.
"""

from __future__ import annotations

import copy
import hashlib
import re


class PIIMasker:
    """Deterministic, reversible masking of account ids within a single case."""

    # PaySim ids: C/M followed by digits. Kept generic in case of other prefixes.
    _ID_RE = re.compile(r"\b[CM]\d{6,}\b")

    def __init__(self) -> None:
        self._to_token: dict[str, str] = {}
        self._to_real: dict[str, str] = {}

    def _token_for(self, real_id: str) -> str:
        if real_id not in self._to_token:
            digest = hashlib.sha256(real_id.encode()).hexdigest()[:6]
            token = f"ACCT_{digest}"
            self._to_token[real_id] = token
            self._to_real[token] = real_id
        return self._to_token[real_id]

    def mask(self, obj):
        """Recursively mask account ids in any str / dict / list structure."""
        if isinstance(obj, str):
            return self._ID_RE.sub(lambda m: self._token_for(m.group()), obj)
        if isinstance(obj, dict):
            return {k: self.mask(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.mask(v) for v in obj]
        return obj

    def unmask(self, obj):
        """Reverse the masking for the final local case file."""
        if isinstance(obj, str):
            for token, real in self._to_real.items():
                obj = obj.replace(token, real)
            return obj
        if isinstance(obj, dict):
            return {k: self.unmask(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.unmask(v) for v in obj]
        return obj

    def masked_copy(self, obj):
        return self.mask(copy.deepcopy(obj))
