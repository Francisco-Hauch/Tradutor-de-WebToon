"""Captura de tela em coordenadas do desktop virtual.

Todo o resto do app -- selecao, OCR, overlay -- trabalha nessas coordenadas,
que sao as do desktop inteiro e nao as de um monitor. Num arranjo com um
monitor a esquerda do principal elas ficam NEGATIVAS, e qualquer codigo que
assuma origem em (0,0) quebra so nesse monitor.
"""

from __future__ import annotations

import logging
import threading

import mss
from PIL import Image

from .types import Rect

log = logging.getLogger(__name__)

# O mss nao e thread-safe: cada thread precisa da sua propria instancia.
_local = threading.local()


def _sct() -> mss.base.MSSBase:
    if getattr(_local, "sct", None) is None:
        _local.sct = mss.mss()
    return _local.sct


def virtual_screen() -> Rect:
    """Retangulo que cobre todos os monitores. Pode ter origem negativa."""
    m = _sct().monitors[0]
    return (m["left"], m["top"], m["width"], m["height"])


def grab(rect: Rect | None = None) -> Image.Image:
    """Captura um retangulo do desktop virtual (ou o desktop todo)."""
    x, y, w, h = rect if rect is not None else virtual_screen()
    if w <= 0 or h <= 0:
        raise ValueError(f"retangulo de captura invalido: {(x, y, w, h)}")

    shot = _sct().grab({"left": x, "top": y, "width": w, "height": h})
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    if _is_blank(image):
        # BitBlt devolve preto em algumas superficies aceleradas ou protegidas.
        # Avisar e melhor do que mandar uma imagem preta para o OCR e relatar
        # "nenhum texto encontrado", que faria parecer falha de leitura.
        log.warning(
            "a captura veio inteiramente preta. Costuma ser aceleracao de hardware ou "
            "conteudo protegido; tente desativar a aceleracao por hardware no navegador."
        )
    return image


def _is_blank(image: Image.Image) -> bool:
    extrema = image.convert("L").getextrema()
    return extrema == (0, 0)
