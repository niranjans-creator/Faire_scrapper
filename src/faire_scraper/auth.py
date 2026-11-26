"""Local dashboard authentication without storing plaintext passwords."""
import hashlib
import hmac
import json
import secrets
from pathlib import Path
from typing import Optional, Set


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        self.sessions: Set[str] = set()

    def configured(self) -> bool:
        return self.path.is_file()

    def _digest(self, password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000).hex()

    def setup(self, password: str) -> bool:
        if self.configured() or len(password) < 10:
            return False
        salt = secrets.token_bytes(16)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"salt": salt.hex(), "digest": self._digest(password, salt)}), encoding="utf-8")
        return True

    def verify(self, password: str) -> bool:
        if not self.configured():
            return False
        data = json.loads(self.path.read_text(encoding="utf-8"))
        expected = self._digest(password, bytes.fromhex(data["salt"]))
        return hmac.compare_digest(expected, data["digest"])

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions.add(token)
        return token

    def valid_session(self, token: Optional[str]) -> bool:
        return bool(token and token in self.sessions)
