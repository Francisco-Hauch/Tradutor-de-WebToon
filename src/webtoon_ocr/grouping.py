"""Transforma as caixas soltas do OCR em baloes.

O detector nao entrega baloes, entrega fragmentos: um espaco no meio da frase
ja e suficiente para "이게 무슨" virar duas caixas, e cada quebra de linha
dentro do balao vira outra. Traduzir esses fragmentos isolados produz frases
sem sentido, entao juntar tudo de volta e pre-requisito da traducao.

Sao duas passadas, nessa ordem:

1. `group_lines`  -- funde fragmentos lado a lado na MESMA linha visual
2. `group_blocks` -- funde linhas empilhadas dentro do MESMO balao

Tudo aqui e funcao pura sobre geometria, sem OCR e sem rede, entao da para
testar de verdade -- que e onde este modulo silenciosamente quebraria.
"""

from __future__ import annotations

from .types import Block, Rect, TextBox


def group(
    boxes: list[TextBox],
    *,
    space_factor: float = 1.5,
    line_overlap: float = 0.4,
    gap_factor: float = 1.0,
    block_overlap: float = 0.25,
) -> list[Block]:
    """Atalho para as duas passadas, na ordem correta."""
    lines = group_lines(boxes, space_factor=space_factor, overlap_ratio=line_overlap)
    return group_blocks(lines, gap_factor=gap_factor, overlap_ratio=block_overlap)


def group_lines(
    boxes: list[TextBox],
    *,
    space_factor: float = 1.5,
    overlap_ratio: float = 0.4,
) -> list[TextBox]:
    """Funde fragmentos horizontalmente vizinhos que estao na mesma linha.

    Mesma linha = as faixas verticais se sobrepoem bastante. Vizinhos = o vao
    horizontal entre eles cabe em poucos caracteres (`space_factor` x altura),
    o que distingue um espaco de uma coluna diferente da pagina.
    """

    def same_line(a: TextBox, b: TextBox) -> bool:
        ax, ay, aw, ah = a.rect
        bx, by, bw, bh = b.rect
        if _overlap_1d(ay, ah, by, bh) < overlap_ratio * min(ah, bh):
            return False
        gap = max(bx - (ax + aw), ax - (bx + bw))
        return gap <= space_factor * min(ah, bh)

    merged = []
    for cluster in _cluster(boxes, same_line):
        cluster.sort(key=lambda b: b.rect[0])  # ordem de leitura: esquerda -> direita
        merged.append(
            TextBox(
                quad=_quad_of(_union(b.rect for b in cluster)),
                text=" ".join(b.text.strip() for b in cluster if b.text.strip()),
                conf=min(b.conf for b in cluster),
            )
        )
    merged.sort(key=lambda b: (b.rect[1], b.rect[0]))
    return merged


def group_blocks(
    lines: list[TextBox],
    *,
    gap_factor: float = 1.0,
    overlap_ratio: float = 0.25,
) -> list[Block]:
    """Funde linhas empilhadas que pertencem ao mesmo balao.

    Mesmo balao = as faixas horizontais se sobrepoem (texto de balao e
    centralizado, entao linhas de um mesmo balao se cobrem) e o vao vertical
    e menor que aproximadamente uma altura de linha.
    """

    def same_block(a: TextBox, b: TextBox) -> bool:
        ax, ay, aw, ah = a.rect
        bx, by, bw, bh = b.rect
        if _overlap_1d(ax, aw, bx, bw) < overlap_ratio * min(aw, bw):
            return False
        gap = max(by - (ay + ah), ay - (by + bh))
        return gap <= gap_factor * min(ah, bh)

    blocks = []
    for cluster in _cluster(lines, same_block):
        cluster.sort(key=lambda b: (b.rect[1], b.rect[0]))  # de cima para baixo
        blocks.append(
            Block(
                rect=_union(b.rect for b in cluster),
                # Espaco, e nao quebra de linha: a quebra dentro do balao e
                # decisao de diagramacao, nao de gramatica. O tradutor precisa
                # receber a frase inteira para nao traduzir pedaco por pedaco.
                source=" ".join(b.text.strip() for b in cluster if b.text.strip()),
                lines=list(cluster),
            )
        )
    blocks.sort(key=lambda b: (b.rect[1], b.rect[0]))
    return blocks


def _cluster(items: list, connected) -> list[list]:
    """Agrupa por conectividade transitiva: A~B e B~C poe os tres no mesmo grupo.

    E o que permite uma linha de tres fragmentos se juntar mesmo quando o
    primeiro e o ultimo estao longe demais para serem vizinhos diretos.
    """
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if find(i) != find(j) and connected(items[i], items[j]):
                parent[find(j)] = find(i)

    groups: dict[int, list] = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return list(groups.values())


def _overlap_1d(a_start: int, a_len: int, b_start: int, b_len: int) -> float:
    """Quanto duas faixas 1D se sobrepoem. Zero quando nao se tocam."""
    return max(0, min(a_start + a_len, b_start + b_len) - max(a_start, b_start))


def _union(rects) -> Rect:
    rects = list(rects)
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects)
    y1 = max(r[1] + r[3] for r in rects)
    return (x0, y0, x1 - x0, y1 - y0)


def _quad_of(rect: Rect) -> list[tuple[int, int]]:
    x, y, w, h = rect
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
