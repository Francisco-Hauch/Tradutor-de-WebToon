"""Selecao de regiao no estilo da Ferramenta de Captura.

Como o texto da webtoon esta dentro da imagem, nao ha o que selecionar de
verdade. O substituto e congelar a tela e deixar voce arrastar um retangulo
sobre o balao ou a pagina.

Congelar importa por dois motivos: o conteudo nao pode rolar entre a hora em
que voce escolhe a area e a hora em que ela e lida, e o retangulo precisa ser
desenhado sobre algo estavel.
"""

from __future__ import annotations

from PIL import Image

from . import capture
from .qtutil import ensure_app, to_qimage
from .types import Rect

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, Signal  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

_MIN_SIDE = 8  # abaixo disso e clique acidental, nao selecao


class _SnipOverlay(QWidget):
    finished = Signal()

    def __init__(self, background: Image.Image, origin: QPoint) -> None:
        super().__init__()
        self._pixmap = QPixmap.fromImage(to_qimage(background))
        self._origin = origin
        self._start: QPoint | None = None
        self._end: QPoint | None = None
        self.result: Rect | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Geometria em coordenadas do desktop virtual, que podem ser negativas.
        self.setGeometry(origin.x(), origin.y(), background.width, background.height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)

        # Escurece tudo; a area selecionada volta ao brilho original.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        sel = self._selection()
        if sel is not None and sel.isValid():
            painter.drawPixmap(sel, self._pixmap, sel)
            painter.setPen(QPen(QColor(90, 170, 255), 2))
            painter.drawRect(sel.adjusted(0, 0, -1, -1))

    def _selection(self) -> QRect | None:
        if self._start is None or self._end is None:
            return None
        return QRect(self._start, self._end).normalized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
            return
        self._start = event.position().toPoint()
        self._end = self._start
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._start is not None:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        sel = self._selection()
        if sel is not None and sel.width() >= _MIN_SIDE and sel.height() >= _MIN_SIDE:
            # De volta para coordenadas do desktop virtual.
            self.result = (
                sel.x() + self._origin.x(),
                sel.y() + self._origin.y(),
                sel.width(),
                sel.height(),
            )
        self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event) -> None:
        self.finished.emit()
        super().closeEvent(event)


def select_region(background: Image.Image | None = None) -> Rect | None:
    """Abre o seletor e devolve o retangulo escolhido, ou None se cancelado.

    `background` permite reaproveitar uma captura ja feita; sem ele, a tela e
    capturada na hora.
    """
    ensure_app()

    origin_x, origin_y, _, _ = capture.virtual_screen()
    if background is None:
        background = capture.grab()

    overlay = _SnipOverlay(background, QPoint(origin_x, origin_y))

    # Loop aninhado, e nao `app.exec()`: o seletor precisa bloquear ate a
    # escolha sem encerrar o QApplication, que o app da bandeja mantem vivo
    # pela sessao inteira. Um `while overlay.isVisible(): processEvents()`
    # tambem bloquearia, mas girando em vazio e queimando um nucleo.
    loop = QEventLoop()
    overlay.finished.connect(loop.quit)

    overlay.show()
    overlay.activateWindow()
    overlay.raise_()
    loop.exec()

    return overlay.result
