"""Metricas de uso, acumuladas entre sessoes num JSON simples.

Cada recorte soma no contador global, guarda os tempos de OCR e de traducao,
conta as palavras do coreano e registra os pares balao -> traducao. O painel
so le o dicionario `data`; quem grava e o App, depois de cada recorte.

Arquivo ausente ou corrompido nao derruba o app: as metricas recomecam do zero.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .config import CACHE_DIR
from .types import Block

log = logging.getLogger(__name__)

METRICS_PATH = CACHE_DIR / "metricas.json"
MAX_TEMPOS = 50
MAX_RECENTES = 200

# ponytail: palavra = trecho com hangul separado por espaco; particulas ficam
# grudadas (사랑을 != 사랑이). Glossario pelo modelo (opcao B da spec) se poluir.
_HANGUL = re.compile(r"[가-힣]+")


def _empty() -> dict:
    return {"recortes": 0, "baloes": 0, "tempos": [], "palavras": {}, "recentes": []}


class Metrics:
    def __init__(self, path: Path = METRICS_PATH) -> None:
        self.path = path
        self.data = _empty()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log.warning("metricas ilegiveis em %s, recomecando: %s", path, exc)

    def record(self, ocr_ms: float, traducao_ms: float, blocks: list[Block]) -> None:
        d = self.data
        d["recortes"] += 1
        d["baloes"] += len(blocks)
        d["tempos"] = (d["tempos"] + [{"ocr_ms": round(ocr_ms), "traducao_ms": round(traducao_ms)}])[-MAX_TEMPOS:]

        for b in blocks:
            for word in _HANGUL.findall(b.source):
                d["palavras"][word] = d["palavras"].get(word, 0) + 1
        novos = [{"ko": b.source, "en": b.translated or ""} for b in reversed(blocks)]
        d["recentes"] = (novos + d["recentes"])[:MAX_RECENTES]

    def top_palavras(self, n: int = 10) -> list[tuple[str, int]]:
        return sorted(self.data["palavras"].items(), key=lambda kv: -kv[1])[:n]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)  # troca atomica: queda no meio nao corrompe o arquivo
