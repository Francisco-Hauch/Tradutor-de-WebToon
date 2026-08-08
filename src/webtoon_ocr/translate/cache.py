"""Cache em SQLite das traducoes ja feitas.

Reler um capitulo, ou passar de novo pelo mesmo balao depois de rolar a
pagina, fica instantaneo em vez de chamar o modelo outra vez. A chave inclui
modelo e idioma, entao trocar qualquer um dos dois nao reaproveita traducao
antiga por engano.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


class TranslationCache:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS translations ("
            " key TEXT PRIMARY KEY,"
            " source TEXT NOT NULL,"
            " result TEXT NOT NULL,"
            " created_at REAL DEFAULT (unixepoch())"
            ")"
        )
        self._db.commit()

    @staticmethod
    def _key(source: str, model: str, target_lang: str) -> str:
        raw = "\x1f".join((source, model, target_lang))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, source: str, model: str, target_lang: str) -> str | None:
        row = self._db.execute(
            "SELECT result FROM translations WHERE key = ?",
            (self._key(source, model, target_lang),),
        ).fetchone()
        return row[0] if row else None

    def put(self, source: str, model: str, target_lang: str, result: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO translations (key, source, result) VALUES (?, ?, ?)",
            (self._key(source, model, target_lang), source, result),
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()
