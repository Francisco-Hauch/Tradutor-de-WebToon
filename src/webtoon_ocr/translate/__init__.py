"""Tradutores, todos atras do mesmo protocolo."""

from __future__ import annotations

from ..config import TranslateConfig
from .base import Translator


def build_translator(cfg: TranslateConfig) -> Translator:
    if cfg.provider == "ollama":
        from .ollama import OllamaTranslator

        return OllamaTranslator(cfg)
    raise ValueError(f"provedor de traducao desconhecido: {cfg.provider!r}")


__all__ = ["Translator", "build_translator"]
