"""Metricas acumulam entre sessoes e sobrevivem a arquivo ruim."""

from __future__ import annotations

from webtoon_ocr.metricas import MAX_TEMPOS, Metrics
from webtoon_ocr.types import Block


def _blk(src: str, en: str) -> Block:
    return Block(rect=(0, 0, 1, 1), source=src, translated=en)


def test_acumula_entre_sessoes(tmp_path):
    path = tmp_path / "m.json"
    m = Metrics(path)
    m.record(800, 1900, [_blk("사랑 해요!", "I love you!"), _blk("사랑", "Love")])
    m.save()

    m2 = Metrics(path)
    m2.record(700, 0, [])
    assert m2.data["recortes"] == 2
    assert m2.data["baloes"] == 2
    assert m2.top_palavras(1) == [("사랑", 2)]
    # ultimo balao da pagina = mais recente, no topo
    assert [r["en"] for r in m2.data["recentes"]] == ["Love", "I love you!"]
    assert m2.data["tempos"][-1] == {"ocr_ms": 700, "traducao_ms": 0}


def test_arquivo_corrompido_recomeca(tmp_path):
    path = tmp_path / "m.json"
    path.write_text("{nao e json", encoding="utf-8")
    assert Metrics(path).data["recortes"] == 0


def test_tempos_limitados(tmp_path):
    m = Metrics(tmp_path / "m.json")
    for i in range(MAX_TEMPOS + 5):
        m.record(i, i, [])
    assert len(m.data["tempos"]) == MAX_TEMPOS
    assert m.data["tempos"][-1]["ocr_ms"] == MAX_TEMPOS + 4
