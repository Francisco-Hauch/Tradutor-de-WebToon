"""Verificacao de disponibilidade das dependencias pesadas, sem carrega-las.

O app precisa subir e mostrar a cara mesmo numa maquina sem Ollama e sem a
stack de OCR (Paddle + CUDA), que pesa varios GB. Este modulo responde, de
forma barata e sem efeitos colaterais, "da para traduzir agora?" -- para o
painel pintar o estado certo e para o aquecimento decidir o que tentar.

Nada aqui importa Paddle nem sobe modelo: OCR e checado por `find_spec` (o
pacote esta instalado?) e Ollama por uma requisicao HTTP curta (o servico
respondeu?). Carregar de verdade continua sendo tarefa do pipeline, na hora.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from enum import Enum

from .config import OcrConfig, TranslateConfig

log = logging.getLogger(__name__)


class State(str, Enum):
    OK = "ok"            # disponivel e pronto para uso
    MISSING = "missing"  # dependencia ausente nesta maquina
    ERROR = "error"      # presente, mas respondeu com erro
    UNKNOWN = "unknown"  # ainda nao verificado


@dataclass
class Component:
    state: State
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state is State.OK


@dataclass
class Health:
    ocr: Component
    ollama: Component

    @property
    def can_translate(self) -> bool:
        """So da para traduzir de verdade se OCR e Ollama estiverem de pe."""
        return self.ocr.ok and self.ollama.ok


def check_ocr(cfg: OcrConfig) -> Component:
    """O motor de OCR escolhido esta instalado? So verifica o import, nao sobe nada."""
    module = {"paddle": "paddleocr", "easyocr": "easyocr"}.get(cfg.engine, cfg.engine)
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        found = False

    if found:
        return Component(State.OK, f"{module} instalado")
    return Component(State.MISSING, f"{module} nao instalado")


def check_ollama(cfg: TranslateConfig, timeout_s: float = 1.5) -> Component:
    """O Ollama respondeu e tem o modelo? Requisicao curta, tolerante a tudo.

    Nunca levanta: qualquer falha vira um estado que o painel sabe pintar.
    """
    if cfg.provider != "ollama":
        return Component(State.UNKNOWN, f"provedor {cfg.provider!r} nao verificado")

    try:
        import httpx
    except ImportError:
        return Component(State.MISSING, "httpx nao instalado")

    try:
        resp = httpx.get(f"{cfg.host}/api/tags", timeout=timeout_s)
        resp.raise_for_status()
    except Exception as exc:  # ConnectError, timeout, HTTP, etc.
        return Component(State.MISSING, f"Ollama nao respondeu em {cfg.host}")

    try:
        models = [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:
        models = []

    # O nome pode vir com tag (":latest"); casa pelo prefixo antes dos dois-pontos.
    wanted = cfg.model.split(":")[0]
    has_model = any(name.split(":")[0] == wanted for name in models)
    if has_model:
        return Component(State.OK, f"modelo {cfg.model} disponivel")
    if models:
        return Component(State.ERROR, f"Ollama de pe, mas sem {cfg.model} (pull pendente)")
    return Component(State.OK, "Ollama de pe")


def check(ocr_cfg: OcrConfig, tr_cfg: TranslateConfig, ollama_timeout_s: float = 1.5) -> Health:
    return Health(
        ocr=check_ocr(ocr_cfg),
        ollama=check_ollama(tr_cfg, timeout_s=ollama_timeout_s),
    )
