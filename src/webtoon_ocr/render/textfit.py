"""Acha o maior corpo de fonte em que a traducao ainda cabe no balao.

O balao tem o tamanho do texto coreano, e o ingles quase nunca ocupa o mesmo
espaco -- costuma ser mais longo. Sem ajuste, ou o texto vaza para fora do
balao ou fica minusculo demais para ler.

Este modulo nao conhece PIL nem Qt: quem chama passa uma funcao `measure`
que sabe medir texto no seu proprio motor de desenho. E o que permite o
render em PNG e o overlay na tela compartilharem exatamente esta logica, e o
que torna o modulo testavel sem abrir janela nenhuma.
"""

from __future__ import annotations

from typing import Callable, Protocol


class Measure(Protocol):
    def __call__(self, text: str, size: int) -> tuple[float, float]:
        """Largura e altura de `text` desenhado no corpo `size`."""
        ...


def wrap(text: str, max_width: float, measure: Callable[[str], float]) -> list[str]:
    """Quebra o texto em linhas que cabem em `max_width`.

    Palavra que sozinha nao cabe e partida no meio -- sem isso, uma palavra
    longa em ingles forcaria o ajuste a diminuir a fonte da frase inteira.
    """
    lines: list[str] = []
    current = ""

    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and measure(candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

        # Checado a cada palavra, e nao so apos uma quebra: a palavra grande
        # demais pode ser a primeira da linha, e ai nao houve quebra alguma.
        if measure(current) > max_width:
            *full, current = _split_long_word(current, max_width, measure)
            lines.extend(full)

    if current:
        lines.append(current)
    return lines or [""]


def _split_long_word(word: str, max_width: float, measure: Callable[[str], float]) -> list[str]:
    parts: list[str] = []
    chunk = ""
    for char in word:
        if chunk and measure(chunk + char) > max_width:
            parts.append(chunk)
            chunk = char
        else:
            chunk += char
    parts.append(chunk)
    return parts


def fit(
    text: str,
    box_width: float,
    box_height: float,
    measure: Measure,
    *,
    min_size: int = 8,
    max_size: int = 40,
    line_spacing: float = 1.15,
) -> tuple[int, list[str]]:
    """Devolve `(corpo_da_fonte, linhas)` -- o maior corpo que ainda cabe.

    Busca binaria: "cabe" e monotonico no tamanho da fonte, entao nao ha
    necessidade de testar tamanho a tamanho.
    """
    if not text.strip() or box_width <= 0 or box_height <= 0:
        return min_size, [""]

    def layout(size: int) -> tuple[list[str], bool]:
        lines = wrap(text, box_width, lambda s: measure(s, size)[0])
        line_h = measure("Ag", size)[1] * line_spacing
        return lines, line_h * len(lines) <= box_height

    best: tuple[int, list[str]] | None = None
    low, high = min_size, max_size
    while low <= high:
        mid = (low + high) // 2
        lines, ok = layout(mid)
        if ok:
            best = (mid, lines)
            low = mid + 1
        else:
            high = mid - 1

    # Nada coube: usa o menor corpo mesmo transbordando. Texto pequeno demais
    # ainda pode ser lido; balao vazio nao ajuda ninguem.
    return best or (min_size, layout(min_size)[0])
