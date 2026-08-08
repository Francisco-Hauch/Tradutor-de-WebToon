"""Tipos compartilhados por todo o pipeline.

O fluxo e sempre o mesmo: o OCR devolve `TextBox` (uma por linha de texto),
o agrupamento funde essas linhas em `Block` (um por balao), e o render
consome `Block`. Tanto o render em PNG quanto o overlay na tela leem
exatamente a mesma lista de `Block`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

Point = tuple[int, int]
Rect = tuple[int, int, int, int]  # x, y, largura, altura


@dataclass
class TextBox:
    """Uma linha de texto detectada pelo OCR."""

    quad: list[Point]  # 4 cantos, em sentido horario a partir do topo-esquerdo
    text: str
    conf: float

    @property
    def rect(self) -> Rect:
        """Bounding box alinhado aos eixos que contem o quad."""
        xs = [p[0] for p in self.quad]
        ys = [p[1] for p in self.quad]
        x0, y0 = min(xs), min(ys)
        return (x0, y0, max(xs) - x0, max(ys) - y0)

    def translated_by(self, dx: int, dy: int) -> TextBox:
        """Copia deslocada -- usada para converter coords do recorte em coords de tela."""
        return TextBox(
            quad=[(x + dx, y + dy) for x, y in self.quad],
            text=self.text,
            conf=self.conf,
        )

    def scaled_by(self, factor: float) -> TextBox:
        """Copia reescalada -- desfaz o upscale aplicado antes do OCR."""
        return TextBox(
            quad=[(round(x * factor), round(y * factor)) for x, y in self.quad],
            text=self.text,
            conf=self.conf,
        )


@dataclass
class Block:
    """Um balao: varias linhas do OCR agrupadas, com sua traducao."""

    rect: Rect
    source: str  # linhas unidas na ordem de leitura
    translated: str | None = None
    lines: list[TextBox] = field(default_factory=list)

    def translated_by(self, dx: int, dy: int) -> Block:
        x, y, w, h = self.rect
        return Block(
            rect=(x + dx, y + dy, w, h),
            source=self.source,
            translated=self.translated,
            lines=[ln.translated_by(dx, dy) for ln in self.lines],
        )
