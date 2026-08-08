"""Testes do agrupamento -- geometria pura, sem OCR e sem rede."""

from __future__ import annotations

import pytest

from webtoon_ocr.grouping import group, group_blocks, group_lines
from webtoon_ocr.types import TextBox


def box(x: int, y: int, w: int, h: int, text: str = "x") -> TextBox:
    return TextBox(quad=[(x, y), (x + w, y), (x + w, y + h), (x, y + h)], text=text, conf=1.0)


class TestGroupLines:
    def test_funde_fragmentos_separados_por_espaco(self):
        # O caso real: um espaco na frase faz o detector cortar em duas caixas.
        lines = group_lines([box(0, 0, 40, 20, "이게"), box(50, 0, 40, 20, "무슨")])
        assert [ln.text for ln in lines] == ["이게 무슨"]
        assert lines[0].rect == (0, 0, 90, 20)

    def test_mantem_separadas_colunas_distantes(self):
        # Mesmo topo, mas do outro lado da pagina: baloes diferentes.
        lines = group_lines([box(0, 0, 40, 20, "a"), box(400, 0, 40, 20, "b")])
        assert len(lines) == 2

    def test_mantem_separadas_linhas_empilhadas(self):
        # Sem sobreposicao vertical: nao sao a mesma linha visual.
        lines = group_lines([box(0, 0, 40, 20, "a"), box(0, 40, 40, 20, "b")])
        assert len(lines) == 2

    def test_conectividade_transitiva(self):
        # a~b e b~c, mas a e c estao longe demais para serem vizinhos diretos.
        lines = group_lines([box(0, 0, 30, 20, "a"), box(45, 0, 30, 20, "b"), box(90, 0, 30, 20, "c")])
        assert [ln.text for ln in lines] == ["a b c"]

    def test_ordena_por_posicao_e_nao_pela_entrada(self):
        lines = group_lines([box(50, 0, 40, 20, "segundo"), box(0, 0, 40, 20, "primeiro")])
        assert lines[0].text == "primeiro segundo"

    def test_confianca_e_a_do_pior_fragmento(self):
        a, b = box(0, 0, 40, 20, "a"), box(50, 0, 40, 20, "b")
        a.conf, b.conf = 0.9, 0.4
        assert group_lines([a, b])[0].conf == pytest.approx(0.4)


class TestGroupBlocks:
    def test_funde_linhas_empilhadas_do_mesmo_balao(self):
        blocks = group_blocks([box(10, 0, 100, 20, "primeira"), box(15, 26, 90, 20, "segunda")])
        assert len(blocks) == 1
        assert blocks[0].source == "primeira segunda"

    def test_separa_baloes_distantes_verticalmente(self):
        blocks = group_blocks([box(10, 0, 100, 20, "a"), box(10, 300, 100, 20, "b")])
        assert len(blocks) == 2

    def test_separa_baloes_lado_a_lado(self):
        # Mesma altura, sem sobreposicao horizontal: baloes diferentes.
        blocks = group_blocks([box(0, 0, 100, 20, "a"), box(400, 0, 100, 20, "b")])
        assert len(blocks) == 2

    def test_junta_com_espaco_e_nao_com_quebra_de_linha(self):
        # A quebra dentro do balao e diagramacao; o tradutor precisa da frase inteira.
        blocks = group_blocks([box(10, 0, 100, 20, "나는 널"), box(12, 26, 90, 20, "믿었어")])
        assert "\n" not in blocks[0].source
        assert blocks[0].source == "나는 널 믿었어"

    def test_rect_cobre_todas_as_linhas(self):
        blocks = group_blocks([box(10, 0, 100, 20), box(20, 30, 60, 20)])
        assert blocks[0].rect == (10, 0, 100, 50)

    def test_preserva_as_linhas_de_origem(self):
        blocks = group_blocks([box(10, 0, 100, 20, "a"), box(10, 26, 100, 20, "b")])
        assert len(blocks[0].lines) == 2


class TestGroupCompleto:
    def test_pagina_com_quatro_baloes(self):
        """Reproduz a saida real do OCR sobre samples/_synthetic.png."""
        boxes = [
            box(124, 70, 153, 40, "안녕하세요"),
            box(108, 113, 183, 37, "오랜만이에요"),
            box(492, 103, 78, 44, "이게"),
            box(548, 103, 82, 45, "무슨"),
            box(506, 146, 110, 40, "일이야?"),
            box(491, 186, 139, 42, "설명해줘"),
            box(179, 320, 115, 51, "나는 널"),
            box(184, 360, 104, 50, "믿었어"),
            box(498, 402, 64, 38, "빨리"),
            box(568, 403, 103, 35, "도망쳐!"),
        ]
        blocks = group(boxes)
        assert [b.source for b in blocks] == [
            "안녕하세요 오랜만이에요",
            "이게 무슨 일이야? 설명해줘",
            "나는 널 믿었어",
            "빨리 도망쳐!",
        ]

    def test_entrada_vazia(self):
        assert group([]) == []

    def test_caixa_unica(self):
        blocks = group([box(0, 0, 50, 20, "oi")])
        assert len(blocks) == 1 and blocks[0].source == "oi"
