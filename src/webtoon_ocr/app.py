"""O produto: uma janela de controle + a bandeja, traduzindo o que voce
selecionar em qualquer app.

Fluxo de um disparo:

    atalho global -> congela a tela -> voce arrasta o retangulo ->
    OCR -> agrupa em baloes -> traduz -> desenha por cima, na tela

A janela ("a cara") mostra o estado, diz se OCR e Ollama estao disponiveis, e
concentra os botoes e ajustes. Fecha-la NAO fecha o app: ele continua na
bandeja. Sair de verdade e pelo botao "Sair".

Nota sobre threads. O overlay e transparente ao mouse e ao teclado, entao ele
nunca recebe eventos: atalho, Esc e rolagem chegam por listeners globais do
pynput, que rodam em threads proprias. Widget de Qt so pode ser tocado na
thread principal, entao essas threads nao mexem em nada -- apenas emitem
sinais, que o Qt entrega na thread principal automaticamente. O OCR e a
traducao, que somam alguns segundos, vao para uma thread de trabalho, senao
a interface congelaria a cada disparo. O aquecimento -- carregar OCR e subir o
modelo -- tambem roda em thread e reporta o andamento por sinais.
"""

from __future__ import annotations

import logging
import sys
import threading

from . import capture
from . import health as health_mod
from .assets import app_icon
from .config import AppConfig, load_config, save_config
from .metricas import Metrics
from .qtutil import ensure_app  # importa cedo: ajusta o DPI antes do Qt
from .render import overlay as overlay_mod
from .selector import select_region
from .types import Block
from .ui.panel import ControlPanel

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QMenu, QSystemTrayIcon  # noqa: E402

log = logging.getLogger(__name__)


class App(QObject):
    # Emitidos das threads de listener/aquecimento; entregues na thread principal.
    _triggered = Signal()
    _dismissed = Signal()
    _ready = Signal(list)
    _failed = Signal(str)
    _status = Signal(str, str, str)   # (estado, texto, detalhe)
    _health = Signal(object)          # health_mod.Health
    _metrics = Signal(object)         # Metrics, depois de cada recorte

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.qt = ensure_app()
        self.qt.setQuitOnLastWindowClosed(False)  # a janela some, o app continua

        self.overlay = overlay_mod.build(cfg.render, capture.virtual_screen())
        self._pipeline = None
        self._busy = False
        self._enabled = True
        self._lock = threading.Lock()
        self.metrics = Metrics()

        self._triggered.connect(self._on_trigger)
        self._dismissed.connect(self._on_dismiss)
        self._ready.connect(self._on_ready)
        self._failed.connect(self._on_failed)
        self._status.connect(self._on_status)
        self._health.connect(self._on_health)
        self._metrics.connect(lambda m: self.panel.set_metrics(m))

        self.panel = self._build_panel()
        self._tray = self._build_tray()
        self._listeners: list = []

    # ---------------------------------------------------------------- setup

    def _build_panel(self) -> ControlPanel:
        panel = ControlPanel(self.cfg, hotkey_label=_pretty(self.cfg.hotkey))
        panel.translate_requested.connect(self._on_trigger)
        panel.clear_requested.connect(self._on_dismiss)
        panel.enabled_toggled.connect(self._set_enabled)
        panel.settings_applied.connect(self._apply_settings)
        panel.quit_requested.connect(self.quit)
        panel.set_status("loading", "Iniciando…", "")
        panel.set_metrics(self.metrics)
        return panel

    def _build_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(app_icon(), self.qt)
        tray.setToolTip(f"Tradutor de Webtoon  ({_pretty(self.cfg.hotkey)})")

        menu = QMenu()
        act_open = QAction("Abrir painel", menu)
        act_open.triggered.connect(self._show_panel)
        act_translate = QAction(f"Traduzir uma area\t{_pretty(self.cfg.hotkey)}", menu)
        act_translate.triggered.connect(self._on_trigger)
        act_clear = QAction("Limpar traducao\tEsc", menu)
        act_clear.triggered.connect(self._on_dismiss)
        act_quit = QAction("Sair", menu)
        act_quit.triggered.connect(self.quit)

        menu.addAction(act_open)
        menu.addAction(act_translate)
        menu.addAction(act_clear)
        menu.addSeparator()
        menu.addAction(act_quit)

        tray.setContextMenu(menu)
        # Clique no icone abre o painel -- e o gesto que as pessoas esperam.
        tray.activated.connect(
            lambda reason: self._show_panel()
            if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick)
            else None
        )
        tray.show()
        return tray

    def _show_panel(self) -> None:
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _start_listeners(self) -> None:
        from pynput import keyboard, mouse

        hotkeys = keyboard.GlobalHotKeys({self.cfg.hotkey: self._on_hotkey})
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

    def _stop_listeners(self) -> None:
        for listener in self._listeners:
            try:
                listener.stop()
            except Exception:
                pass
        self._listeners = []

    def _on_hotkey(self) -> None:
        # O atalho so dispara quando o app esta "ativo"; o botao/menu sempre disparam.
        if self._enabled:
            self._triggered.emit()

    def _warmup(self) -> None:
        """Verifica dependencias e, se der, sobe OCR e modelo antes do 1o uso.

        Numa maquina sem Ollama ou sem a stack de OCR (o caso comum de quem so
        quer ver o app rodando), nao ha o que carregar: a checagem barata
        detecta isso, o painel pinta o estado, e nada de pesado e importado --
        o app fica de pe, so sem traduzir.
        """

        def work():
            self._emit_status("loading", "Verificando dependências…", "")
            health = health_mod.check(self.cfg.ocr, self.cfg.translate)
            self._health.emit(health)

            if not health.ocr.ok:
                self._emit_status(
                    "error", "OCR indisponível",
                    f"{health.ocr.detail} — instale a stack de OCR para traduzir",
                )
                return
            if not health.ollama.ok:
                self._emit_status(
                    "error", "Ollama não encontrado",
                    "rode o Ollama e baixe o modelo para traduzir",
                )
                return

            self._emit_status("loading", "Carregando modelos…", "primeira vez leva ~1 min")
            try:
                from .pipeline import build

                self._pipeline = build(self.cfg)
                self._pipeline.translator.translate(["안녕"])  # sobe o modelo
                log.info("pronto: OCR e modelo de traducao carregados")
                self._emit_status("ready", "Pronto", "OCR e modelo de tradução carregados")
            except Exception as exc:  # noqa: BLE001
                log.error("falha no aquecimento: %s", exc)
                self._emit_status("error", "Falha ao carregar", str(exc)[:120])

        self._emit_status("loading", "Iniciando…", "")
        threading.Thread(target=work, daemon=True).start()

    # -------------------------------------------------------------- acoes

    def _emit_status(self, state: str, text: str, detail: str) -> None:
        self._status.emit(state, text, detail)

    def _on_status(self, state: str, text: str, detail: str) -> None:
        self.panel.set_status(state, text, detail)
        tip = f"Tradutor de Webtoon — {text}"
        self._tray.setToolTip(tip)

    def _on_health(self, health) -> None:
        self.panel.set_health(health)

    def _set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._emit_status("ready" if self._pipeline else "idle", "Ativo", "atalho global ligado")
        else:
            self._emit_status("disabled", "Pausado", "atalho global desligado")

    def _apply_settings(self, values: dict) -> None:
        new_hotkey = values.get("hotkey", self.cfg.hotkey)
        hotkey_changed = new_hotkey != self.cfg.hotkey

        self.cfg.hotkey = new_hotkey
        self.cfg.translate.use_vision = bool(values.get("use_vision", self.cfg.translate.use_vision))
        self.cfg.ocr.device = values.get("device", self.cfg.ocr.device)

        try:
            path = save_config(self.cfg)
            log.info("config salva em %s", path)
        except Exception as exc:  # noqa: BLE001
            log.error("nao consegui salvar a config: %s", exc)
            self._emit_status("error", "Não salvou a config", str(exc)[:120])
            return

        if hotkey_changed and self._listeners:
            self._stop_listeners()
            self._start_listeners()
        self.panel.set_hotkey_label(_pretty(self.cfg.hotkey))
        self._emit_status(
            "ready" if self._pipeline else "idle",
            "Ajustes salvos",
            "device/use_vision valem no próximo carregamento" if self._pipeline else "",
        )

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
            self._record_metrics(blocks)
            # Do espaco do recorte para o espaco da tela, que e onde o
            # overlay desenha.
            self._ready.emit([b.translated_by(rect[0], rect[1]) for b in blocks])
        except Exception as exc:
            log.exception("falha na traducao")
            self._failed.emit(str(exc))

    def _record_metrics(self, blocks: list[Block]) -> None:
        # Metrica nunca pode derrubar a traducao: falhou, loga e segue.
        try:
            self.metrics.record(*self._pipeline.last_timing, blocks)
            self.metrics.save()
        except Exception:  # noqa: BLE001
            log.exception("nao consegui gravar as metricas")
        self._metrics.emit(self.metrics)

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
        self._stop_listeners()
        self.overlay.clear()
        self._tray.hide()
        self.panel.request_real_close()
        self.qt.quit()

    def run(self) -> int:
        self._start_listeners()
        self._show_panel()   # abre a cara ao iniciar
        self._warmup()
        log.info("na bandeja. %s para traduzir, Esc para limpar.", _pretty(self.cfg.hotkey))
        return self.qt.exec()


def _pretty(hotkey: str) -> str:
    """'<ctrl>+<alt>+q' -> 'Ctrl+Alt+Q'. A sintaxe do pynput nao e para ser lida."""
    return "+".join(part.strip("<>").capitalize() for part in hotkey.split("+"))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("paddlex").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return App(load_config()).run()


if __name__ == "__main__":
    sys.exit(main())
