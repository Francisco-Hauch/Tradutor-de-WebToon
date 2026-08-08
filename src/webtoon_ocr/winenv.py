"""Ajustes de Windows que precisam acontecer ANTES de qualquer coisa grafica.

Este e o modulo que evita o bug classico deste tipo de app: com a tela em
escala diferente de 100%, o `mss` captura em pixels FISICOS enquanto o Qt
desenha em pixels LOGICOS. As duas coordenadas nao batem, e o overlay
aparece deslocado e menor que os baloes -- um erro que so se manifesta na
ultima fase e parece um bug de calculo, nao de configuracao.

A correcao e declarar o processo per-monitor-aware e desligar o
escalonamento do Qt, para que os dois lados falem em pixels fisicos.
"""

from __future__ import annotations

import ctypes
import logging
import os

log = logging.getLogger(__name__)

# SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)
_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

_done = False


def setup() -> None:
    """Idempotente e obrigatoria antes de criar o QApplication."""
    global _done
    if _done:
        return
    _done = True

    # Sem isto o Qt reescalaria a janela, e as coordenadas do overlay
    # deixariam de coincidir com as da captura.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")

    for attempt in (
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(_PER_MONITOR_AWARE_V2),
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),  # Windows 8.1
        lambda: ctypes.windll.user32.SetProcessDPIAware(),  # Windows 7
    ):
        try:
            if attempt():
                return
        except (AttributeError, OSError):
            continue

    log.warning("nao foi possivel declarar DPI awareness; o overlay pode sair deslocado")
