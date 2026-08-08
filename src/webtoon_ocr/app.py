"""O produto: fica na bandeja e traduz o que voce selecionar, em qualquer app.

Fluxo de um disparo:

    atalho global -> congela a tela -> voce arrasta o retangulo ->
    OCR -> agrupa em baloes -> traduz -> desenha por cima, na tela

Nota sobre threads. O overlay e transparente ao mouse e ao teclado, entao ele
nunca recebe eventos: atalho, Esc e rolagem chegam por listeners globais do
pynput, que rodam em threads proprias. Widget de Qt so pode ser tocado na
thread principal, entao essas threads nao mexem em nada -- apenas emitem
sinais, que o Qt entrega na thread principal automaticamente. O OCR e a
traducao, que somam alguns segundos, vao para uma thread de trabalho, senao
a interface congelaria a cada disparo.
"""

from __future__ import annotations

import logging
import sys
import threading

from . import capture
from .config import AppConfig, load_config
from .qtutil import ensure_app  # importa cedo: ajusta o DPI antes do Qt
from .render import overlay as overlay_mod
from .selector import select_region
from .types import Block

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QMenu, QSystemTrayIcon  # noqa: E402

log = logging.getLogger(__name__)


class App(QObject):
    # Emitidos das threads de listener; entregues na thread principal.
    _triggered = Signal()
    _dismissed = Signal()
    _ready = Signal(list)
    _failed = Signal(str)

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.qt = ensure_app()
        self.qt.setQuitOnLastWindowClosed(False)  # a janela some, o app continua

        self.overlay = overlay_mod.build(cfg.render, capture.virtual_screen())
        self._pipeline = None
        self._busy = False
        self._lock = threading.Lock()

        self._triggered.connect(self._on_trigger)
        self._dismissed.connect(self._on_dismiss)
        self._ready.connect(self._on_ready)
        self._failed.connect(self._on_failed)

        self._tray = self._build_tray()
        self._listeners: list = []

    # ---------------------------------------------------------------- setup

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(_icon(), self.qt)
        tray.setToolTip(f"Tradutor de webtoon  ({_pretty(self.cfg.hotkey)})")

        menu = QMenu()
        act_translate = QAction(f"Traduzir uma area\t{_pretty(self.cfg.hotkey)}", menu)
        act_translate.triggered.connect(self._on_trigger)
        act_clear = QAction("Limpar traducao\tEsc", menu)
        act_clear.triggered.connect(self._on_dismiss)
        act_quit = QAction("Sair", menu)
        act_quit.triggered.connect(self.quit)

        menu.addAction(act_translate)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self._on_trigger() if reason == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        tray.show()
        return tray

    def _start_listeners(self) -> None:
        from pynput import keyboard, mouse

        hotkeys = keyboard.GlobalHotKeys({self.cfg.hotkey: self._triggered.emit})
        hotkeys.daemon = True
        hotkeys.start()

        def on_press(key):
            if key == keyboard.Key.esc:
                self._dismissed.emit()

        keys = keyboard.Listener(on_press=on_press)
        keys.daemon = True
        keys.start()

        # Rolar a pagina desloca o conteudo: a traducao desenhada deixa de
        # corresponder ao que esta embaixo, entao ela tem que sumir.
        mice = mouse.Listener(on_scroll=lambda *_: self._dismissed.emit())
        mice.daemon = True
        mice.start()

        self._listeners = [hotkeys, keys, mice]

    def _warmup(self) -> None:
        """Carrega OCR e sobe o modelo na VRAM antes do primeiro uso.

        Sem isto, o primeiro disparo pagaria ~80s de carregamento do modelo
        e pareceria que o app travou.
        """

        def work():
            try:
                from .pipeline import build

                self._pipeline = build(self.cfg)
                self._pipeline.translator.translate(["안녕"])  # sobe o modelo
                log.info("pronto: OCR e modelo de traducao carregados")
                self._tray.setToolTip(f"Tradutor de webtoon - pronto  ({self.cfg.hotkey})")
            except Exception as exc:
                log.error("falha no aquecimento: %s", exc)
                self._tray.setToolTip(f"Tradutor de webtoon - erro: {exc}")

        self._tray.setToolTip("Tradutor de webtoon - carregando modelos...")
        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- acoes

    def _on_trigger(self) -> None:
        with self._lock:
            if self._busy:
                return
            self._busy = True

        started = False
        try:
            self.overlay.clear()
            screen = capture.grab()
            rect = select_region(screen)
            if rect is None:
                return

            ox, oy, _, _ = capture.virtual_screen()
            x, y, w, h = rect
            # Recorta do quadro congelado, e nao de uma nova captura: entre a
            # selecao e a leitura a pagina pode ter rolado.
            crop = screen.crop((x - ox, y - oy, x - ox + w, y - oy + h))

            self.overlay.show_status("traduzindo...", rect)
            threading.Thread(target=self._work, args=(crop, rect), daemon=True).start()
            started = True
        except Exception as exc:
            log.exception("falha ao iniciar a traducao")
            self.overlay.show_status(f"erro: {str(exc)[:90]}")
        finally:
            # Se a thread de trabalho arrancou, e ela quem libera o busy ao
            # terminar. Nos demais casos -- inclusive cancelamento com Esc --
            # liberamos aqui, senao o atalho ficaria morto pelo resto da sessao.
            if not started:
                self._busy = False

    def _work(self, crop, rect) -> None:
        try:
            if self._pipeline is None:
                from .pipeline import build

                self._pipeline = build(self.cfg)

            blocks = self._pipeline.run(crop)
            # Do espaco do recorte para o espaco da tela, que e onde o
            # overlay desenha.
            self._ready.emit([b.translated_by(rect[0], rect[1]) for b in blocks])
        except Exception as exc:
            log.exception("falha na traducao")
            self._failed.emit(str(exc))

    def _on_ready(self, blocks: list[Block]) -> None:
        self._busy = False
        if blocks:
            self.overlay.show_blocks(blocks)
        else:
            self.overlay.show_status("nenhum texto encontrado")

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self.overlay.show_status(f"erro: {message[:90]}")

    def _on_dismiss(self) -> None:
        self.overlay.clear()

    def quit(self) -> None:
        for listener in self._listeners:
            listener.stop()
        self.overlay.clear()
        self._tray.hide()
        self.qt.quit()

    def run(self) -> int:
        self._start_listeners()
        self._warmup()
        log.info("na bandeja. %s para traduzir, Esc para limpar.", _pretty(self.cfg.hotkey))
        return self.qt.exec()


def _pretty(hotkey: str) -> str:
    """'<ctrl>+<alt>+q' -> 'Ctrl+Alt+Q'. A sintaxe do pynput nao e para ser lida."""
    return "+".join(part.strip("<>").capitalize() for part in hotkey.split("+"))


def _icon() -> QIcon:
    """Icone desenhado em codigo, para o projeto nao depender de um arquivo."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(40, 120, 220))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(4, 8, 56, 40, 10, 10)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawEllipse(20, 22, 10, 10)
    painter.drawEllipse(36, 22, 10, 10)
    painter.end()

    return QIcon(pixmap)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("paddlex").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return App(load_config()).run()


if __name__ == "__main__":
    sys.exit(main())
