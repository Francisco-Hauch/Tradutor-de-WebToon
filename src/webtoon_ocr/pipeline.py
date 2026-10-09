"""O caminho completo: imagem -> baloes traduzidos.

Existe para que a CLI e o app da bandeja executem exatamente a mesma coisa.
Os motores sao recebidos prontos porque carregar o OCR custa alguns segundos
e subir o modelo de traducao custa mais de um minuto: no app eles vivem pela
sessao inteira e sao reaproveitados a cada recorte.
"""

from __future__ import annotations

import logging
import time

from PIL import Image

from .config import AppConfig
from .grouping import group
from .ocr import OcrEngine
from .translate import Translator
from .types import Block

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, cfg: AppConfig, engine: OcrEngine, translator: Translator) -> None:
        self.cfg = cfg
        self.engine = engine
        self.translator = translator
        # (ocr_ms, traducao_ms) do ultimo run, lido pelo painel de metricas.
        self.last_timing: tuple[float, float] = (0.0, 0.0)

    def run(self, image: Image.Image) -> list[Block]:
        started = time.perf_counter()
        boxes = self.engine.read(image)
        t_ocr = time.perf_counter()

        blocks = group(boxes)
        if not blocks:
            self.last_timing = ((t_ocr - started) * 1000, 0.0)
            log.info("nenhum texto encontrado (%.2fs)", t_ocr - started)
            return []

        # A imagem vai junto: o tradutor multimodal a usa para corrigir o que
        # o OCR leu errado antes de traduzir.
        translations = self.translator.translate([b.source for b in blocks], image)
        for block, translated in zip(blocks, translations):
            block.translated = translated

        self.last_timing = ((t_ocr - started) * 1000, (time.perf_counter() - t_ocr) * 1000)
        log.info(
            "%d linha(s) -> %d balao(oes) | ocr %.2fs, traducao %.2fs",
            len(boxes), len(blocks), t_ocr - started, time.perf_counter() - t_ocr,
        )
        return blocks


def build(cfg: AppConfig) -> Pipeline:
    from .ocr import build_engine
    from .translate import build_translator

    return Pipeline(cfg, build_engine(cfg.ocr), build_translator(cfg.translate))
