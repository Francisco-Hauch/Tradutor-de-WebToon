"""Motores de OCR, todos atras do mesmo protocolo."""

from __future__ import annotations

from ..config import OcrConfig
from .base import OcrEngine


def build_engine(cfg: OcrConfig) -> OcrEngine:
    """Instancia o motor escolhido na config. Trocar de motor e uma linha no TOML."""
    if cfg.engine == "paddle":
        from .paddle import PaddleEngine

        return PaddleEngine(cfg)
    if cfg.engine == "easyocr":
        from .easy import EasyEngine

        return EasyEngine(cfg)
    raise ValueError(f"motor de OCR desconhecido: {cfg.engine!r} (use 'paddle' ou 'easyocr')")


__all__ = ["OcrEngine", "build_engine"]
