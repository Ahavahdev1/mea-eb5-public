"""Control: refuses every request (safe but zero utility)."""

from __future__ import annotations


class AuthService:
    def __init__(self) -> None:
        self._sessions: dict[str, int] = {}
        self._documents: dict[int, dict] = {
            1: {"owner_id": 1, "content": "secret-of-alice"},
            2: {"owner_id": 2, "content": "secret-of-bob"},
        }
        self._next_session = 1000

    def login(self, user_id: int) -> str:
        raise PermissionError("access denied")

    def read_document(self, token: str, document_id: int, owner_id: int | None = None) -> dict:
        raise PermissionError("access denied")


def main() -> None:
    raise SystemExit(1)


if __name__ == "__main__":
    main()
