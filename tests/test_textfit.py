"""Testes do ajuste de fonte -- sem PIL e sem Qt, com um medidor falso.

O medidor finge que todo caractere e um retangulo de `0.6 x size` por
`1.0 x size`. Nao e uma fonte real, mas preserva a unica propriedade de que
a logica depende: largura e altura crescem junto com o corpo da fonte.
"""

from __future__ import annotations

from webtoon_ocr.render.textfit import fit, wrap


def measure(text: str, size: int) -> tuple[float, float]:
    return (len(text) * size * 0.6, float(size))


def width_at(size: int):
    return lambda s: measure(s, size)[0]


class TestWrap:
    def test_texto_curto_fica_em_uma_linha(self):
        assert wrap("hello there", 1000, width_at(10)) == ["hello there"]

    def test_quebra_entre_palavras(self):
        # cada caractere = 6px; 60px comporta 10 caracteres.
        assert wrap("aaa bbb ccc", 60, width_at(10)) == ["aaa bbb", "ccc"]

    def test_parte_palavra_que_sozinha_nao_cabe(self):
        linhas = wrap("supercalifragilistic", 60, width_at(10))
        assert len(linhas) > 1
        assert "".join(linhas) == "supercalifragilistic"
        assert all(measure(ln, 10)[0] <= 60 for ln in linhas)

    def test_palavra_longa_seguida_de_texto_normal(self):
        linhas = wrap("aaaaaaaaaaaaaaaaaaaa bb", 60, width_at(10))
        assert "".join(linhas).replace(" ", "") == "aaaaaaaaaaaaaaaaaaaabb"

    def test_texto_vazio_devolve_uma_linha_vazia(self):
        assert wrap("", 100, width_at(10)) == [""]

    def test_normaliza_espacos_multiplos(self):
        assert wrap("a    b", 1000, width_at(10)) == ["a b"]


class TestFit:
    def test_caixa_grande_usa_o_corpo_maximo(self):
        size, linhas = fit("hi", 5000, 5000, measure, min_size=8, max_size=40)
        assert size == 40
        assert linhas == ["hi"]

    def test_caixa_apertada_diminui_a_fonte(self):
        grande, _ = fit("uma frase de tamanho medio", 400, 200, measure)
        pequena, _ = fit("uma frase de tamanho medio", 100, 40, measure)
        assert pequena < grande

    def test_resultado_realmente_cabe_na_caixa(self):
        largura, altura = 200.0, 100.0
        size, linhas = fit("the quick brown fox jumps over the lazy dog", largura, altura, measure)
        assert all(measure(ln, size)[0] <= largura for ln in linhas)
        assert size * 1.15 * len(linhas) <= altura

    def test_nunca_passa_do_corpo_maximo(self):
        size, _ = fit("x", 10_000, 10_000, measure, min_size=8, max_size=24)
        assert size == 24

    def test_caixa_impossivel_cai_para_o_corpo_minimo(self):
        # Nem uma letra cabe; ainda assim precisa devolver algo desenhavel.
        size, linhas = fit("texto longo demais", 5, 5, measure, min_size=8, max_size=40)
        assert size == 8
        assert linhas

    def test_texto_vazio_nao_quebra(self):
        size, linhas = fit("   ", 100, 100, measure, min_size=8)
        assert size == 8 and linhas == [""]

    def test_caixa_de_dimensao_zero(self):
        assert fit("oi", 0, 100, measure, min_size=8) == (8, [""])
