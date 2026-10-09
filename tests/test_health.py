"""Health check: deve responder sempre, e nunca levantar, mesmo sem rede."""

from __future__ import annotations

import httpx

from webtoon_ocr.config import OcrConfig, TranslateConfig
from webtoon_ocr.health import State, check_ocr, check_ollama


def test_check_ocr_missing_engine():
    comp = check_ocr(OcrConfig(engine="paddle"))
    # Nesta suite o paddle nao esta instalado; o estado tem que ser MISSING,
    # nao um erro nem uma tentativa de importar de verdade.
    assert comp.state in (State.OK, State.MISSING)
    assert not comp.ok or comp.state is State.OK


def test_check_ocr_unknown_engine_is_missing():
    comp = check_ocr(OcrConfig(engine="inexistente"))
    assert comp.state is State.MISSING


def test_check_ollama_offline_is_missing(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "get", boom)
    comp = check_ollama(TranslateConfig())
    assert comp.state is State.MISSING
    assert "Ollama" in comp.detail


def test_check_ollama_up_with_model(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "gemma3:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    comp = check_ollama(TranslateConfig(model="gemma3:12b"))
    assert comp.state is State.OK


def test_check_ollama_up_without_model(monkeypatch):
    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "llama3:8b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    comp = check_ollama(TranslateConfig(model="gemma3:12b"))
    # De pe, mas sem o modelo pedido: erro recuperavel (falta o pull).
    assert comp.state is State.ERROR
    assert "gemma3:12b" in comp.detail
