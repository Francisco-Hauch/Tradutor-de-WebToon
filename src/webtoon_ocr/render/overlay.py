"""Janela transparente que desenha a traducao por cima de qualquer aplicativo.

Cobre o desktop virtual inteiro, nao tem borda, fica sempre no topo e e
TRANSPARENTE AO MOUSE: cliques, rolagem e selecao atravessam e chegam no
navegador normalmente. Sem isso o overlay sequestraria a pagina e voce nao
conseguiria continuar lendo.

Desenha os mesmos `Block` que o render em PNG, com o mesmo ajuste de fonte --
so muda o motor de desenho.
"""

from __future__ import annotations

from ..config import RenderConfig
from ..qtutil import ensure_app
from ..types import Block, Rect
from .textfit import fit

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

_BOX_FILL = QColor(255, 255, 255, 244)
_BOX_EDGE = QColor(150, 150, 150, 200)
_TEXT = QColor(12, 12, 12)
_STATUS_FILL = QColor(24, 24, 28, 225)
_STATUS_TEXT = QColor(240, 240, 245)


def _measurer(family: str):
    """Funcao `measure` do textfit, medindo com as metricas do proprio Qt."""

    def measure(text: str, size: int) -> tuple[float, float]:
        font = QFont(family)
        font.setPixelSize(size)
        fm = QFontMetricsF(font)
        return (fm.horizontalAdvance(text), fm.height())

    return measure


class Overlay(QWidget):
    def __init__(self, cfg: RenderConfig, screen: Rect) -> None:
        super().__init__()
        self.cfg = cfg
        self._origin = (screen[0], screen[1])
        self._blocks: list[Block] = []
        self._status: str | None = None
        self._status_rect: Rect | None = None
        self._measure = _measurer(cfg.font_family)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            # O que faz o mouse atravessar a janela.
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Mostrar sem roubar o foco da janela que voce esta lendo.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(*screen)

    def show_blocks(self, blocks: list[Block]) -> None:
        self._blocks = blocks
        self._status = None
        self._refresh()

    def show_status(self, text: str, near: Rect | None = None) -> None:
        """Aviso curto ('traduzindo...') para a espera nao parecer travamento."""
        self._status = text
        self._status_rect = near
        self._refresh()

    def clear(self) -> None:
        self._blocks = []
        self._status = None
        self.hide()

    def _refresh(self) -> None:
        if not self.isVisible():
            self.show()
            self.raise_()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        for block in self._blocks:
            self._paint_block(painter, block)
        if self._status:
            self._paint_status(painter, self._status)

    def _paint_block(self, painter: QPainter, block: Block) -> None:
        text = (block.translated or "").strip()
        if not text:
            return

        x, y, w, h = self._to_local(block.rect)
        pad = self.cfg.box_padding
        box = QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)

        painter.setBrush(_BOX_FILL)
        painter.setPen(QPen(_BOX_EDGE, 1))
        painter.drawRoundedRect(box, self.cfg.corner_radius, self.cfg.corner_radius)

        inner = box.adjusted(pad, pad, -pad, -pad)
        size, lines = fit(
            text, inner.width(), inner.height(), self._measure,
            min_size=self.cfg.min_font_pt, max_size=self.cfg.max_font_pt,
        )

        font = QFont(self.cfg.font_family)
        font.setPixelSize(size)
        painter.setFont(font)
        painter.setPen(_TEXT)

        line_h = QFontMetricsF(font).height() * 1.15
        top = inner.top() + max(0.0, (inner.height() - line_h * len(lines)) / 2)
        for i, line in enumerate(lines):
            painter.drawText(
                QRectF(inner.left(), top + i * line_h, inner.width(), line_h),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                line,
            )

    def _paint_status(self, painter: QPainter, text: str) -> None:
        font = QFont(self.cfg.font_family)
        font.setPixelSize(16)
        painter.setFont(font)

        fm = QFontMetricsF(font)
        w, h = fm.horizontalAdvance(text) + 28, fm.height() + 16

        if self._status_rect is not None:
            rx, ry, rw, _ = self._to_local(self._status_rect)
            x, y = rx + (rw - w) / 2, ry - h - 8
        else:
            x, y = (self.width() - w) / 2, 40
        # Nao deixa o aviso sair da tela quando a selecao encosta na borda.
        x = min(max(8.0, x), self.width() - w - 8)
        y = min(max(8.0, y), self.height() - h - 8)

        painter.setBrush(_STATUS_FILL)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(x, y, w, h), 10, 10)
        painter.setPen(_STATUS_TEXT)
        painter.drawText(QRectF(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)

    def _to_local(self, rect: Rect) -> Rect:
        """Coords do desktop virtual -> coords da janela (origem pode ser negativa)."""
        x, y, w, h = rect
        return (x - self._origin[0], y - self._origin[1], w, h)


def build(cfg: RenderConfig, screen: Rect) -> Overlay:
    ensure_app()
    return Overlay(cfg, screen)
