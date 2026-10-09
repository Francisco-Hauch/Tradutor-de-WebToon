"""A cara do app: um painel de controle de verdade.

Ate aqui o app so tinha o icone da bandeja -- nenhuma janela. Este painel da
rosto ao produto: mostra o estado (carregando / pronto / erro), diz numa
olhada se OCR e Ollama estao disponiveis nesta maquina, dispara e limpa a
traducao, e deixa ajustar o atalho e os ajustes que o usuario mais mexe.

Nao conhece o App diretamente: fala por sinais Qt (para o App conectar) e
recebe estado por `set_status`/`set_health`. Assim da para abri-lo isolado
para inspecao visual, sem bandeja, sem OCR e sem rede -- que e como ele foi
validado.

Fechar a janela NAO fecha o app: esconde para a bandeja. Sair de verdade so
pelo botao da bandeja ou pelo "Sair" daqui.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..assets import app_icon
from ..config import AppConfig
from ..health import Component, Health, State

# Cores de estado, reaproveitadas pelo ponto de status e pelos indicadores.
_COLORS = {
    "loading": "#E0A030",
    "ready": "#2F9E44",
    "error": "#E03131",
    "idle": "#4C6EF5",
    "disabled": "#868E96",
}

_STYLE = """
QWidget#panel {
    background: #F5F7FA;
}
QLabel { color: #1F2933; }
QLabel#title { font-size: 18px; font-weight: 600; }
QLabel#subtitle { color: #67727E; font-size: 12px; }
QLabel#statusText { font-size: 15px; font-weight: 600; }
QLabel#statusDetail { color: #67727E; font-size: 12px; }
QFrame#card {
    background: #FFFFFF;
    border: 1px solid #E3E8EE;
    border-radius: 12px;
}
QLabel#sectionLabel { color: #9AA5B1; font-size: 11px; font-weight: 600; }
QPushButton {
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 13px;
    background: #FFFFFF;
    border: 1px solid #CBD2D9;
    color: #1F2933;
}
QPushButton:hover { background: #F0F3F7; }
QPushButton:disabled { color: #B4BCC4; background: #F5F7FA; }
QPushButton#primary {
    background: #2878DC;
    border: 1px solid #2878DC;
    color: #FFFFFF;
    font-weight: 600;
    padding: 11px 14px;
    font-size: 14px;
}
QPushButton#primary:hover { background: #1F66C0; }
QPushButton#primary:disabled { background: #A9C4E8; border-color: #A9C4E8; color: #EDF2FA; }
QLineEdit, QComboBox {
    border: 1px solid #CBD2D9;
    border-radius: 8px;
    padding: 6px 8px;
    background: #FFFFFF;
    font-size: 13px;
}
QCheckBox { font-size: 13px; color: #1F2933; }
QLabel#footer { color: #9AA5B1; font-size: 11px; }
"""


def _dot(color: str, size: int = 12) -> QLabel:
    dot = QLabel()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return dot


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return frame, lay


class ControlPanel(QWidget):
    """Janela de controle. Emite sinais; o App conecta e responde."""

    translate_requested = Signal()
    clear_requested = Signal()
    enabled_toggled = Signal(bool)
    settings_applied = Signal(dict)   # {"hotkey", "use_vision", "device"}
    quit_requested = Signal()

    def __init__(self, cfg: AppConfig, hotkey_label: str = "") -> None:
        super().__init__()
        self.cfg = cfg
        self._hotkey_label = hotkey_label or cfg.hotkey
        self._allow_close = False

        self.setObjectName("panel")
        self.setWindowTitle("Tradutor de Webtoon")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(_STYLE)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(14)

        root.addLayout(self._build_header())
        root.addWidget(self._build_status_card())
        root.addWidget(self._build_health_card())
        root.addLayout(self._build_actions())
        root.addWidget(self._build_settings_card())
        root.addWidget(self._build_footer())

    # -------------------------------------------------------------- construcao

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(44, 44))
        row.addWidget(logo)

        texts = QVBoxLayout()
        texts.setSpacing(0)
        title = QLabel("Tradutor de Webtoon")
        title.setObjectName("title")
        subtitle = QLabel("coreano → inglês, direto na tela")
        subtitle.setObjectName("subtitle")
        texts.addWidget(title)
        texts.addWidget(subtitle)
        row.addLayout(texts)
        row.addStretch(1)
        return row

    def _build_status_card(self) -> QFrame:
        frame, lay = _card()
        row = QHBoxLayout()
        row.setSpacing(10)

        self._status_dot = _dot(_COLORS["idle"], 14)
        row.addWidget(self._status_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(1)
        self._status_text = QLabel("Iniciando…")
        self._status_text.setObjectName("statusText")
        self._status_detail = QLabel("")
        self._status_detail.setObjectName("statusDetail")
        col.addWidget(self._status_text)
        col.addWidget(self._status_detail)
        row.addLayout(col)
        row.addStretch(1)
        lay.addLayout(row)
        return frame

    def _build_health_card(self) -> QFrame:
        frame, lay = _card()
        label = QLabel("DEPENDÊNCIAS")
        label.setObjectName("sectionLabel")
        lay.addWidget(label)

        self._ocr_dot = _dot(_COLORS["disabled"])
        self._ocr_detail = QLabel("verificando…")
        self._ocr_detail.setObjectName("statusDetail")
        lay.addLayout(self._health_row(self._ocr_dot, "OCR (PaddleOCR)", self._ocr_detail))

        self._ollama_dot = _dot(_COLORS["disabled"])
        self._ollama_detail = QLabel("verificando…")
        self._ollama_detail.setObjectName("statusDetail")
        lay.addLayout(self._health_row(self._ollama_dot, "Tradução (Ollama)", self._ollama_detail))
        return frame

    def _health_row(self, dot: QLabel, name: str, detail: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(QLabel(name))
        row.addStretch(1)
        detail.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(detail)
        return row

    def _build_actions(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(8)
        self._btn_translate = QPushButton(f"Traduzir uma área    {self._hotkey_label}")
        self._btn_translate.setObjectName("primary")
        self._btn_translate.clicked.connect(self.translate_requested.emit)
        col.addWidget(self._btn_translate)

        self._btn_clear = QPushButton("Limpar tradução (Esc)")
        self._btn_clear.clicked.connect(self.clear_requested.emit)
        col.addWidget(self._btn_clear)
        return col

    def _build_settings_card(self) -> QFrame:
        frame, lay = _card()
        label = QLabel("AJUSTES")
        label.setObjectName("sectionLabel")
        lay.addWidget(label)

        hk_row = QHBoxLayout()
        hk_row.setSpacing(8)
        hk_row.addWidget(QLabel("Atalho"))
        self._hotkey_edit = QLineEdit(self.cfg.hotkey)
        self._hotkey_edit.setPlaceholderText("<ctrl>+<alt>+q")
        hk_row.addWidget(self._hotkey_edit, 1)
        lay.addLayout(hk_row)

        self._chk_vision = QCheckBox("Corrigir o OCR pela imagem antes de traduzir (use_vision)")
        self._chk_vision.setChecked(self.cfg.translate.use_vision)
        lay.addWidget(self._chk_vision)

        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_row.addWidget(QLabel("Dispositivo do OCR"))
        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "gpu", "cpu"])
        current = self.cfg.ocr.device if self.cfg.ocr.device in ("auto", "gpu", "cpu") else "auto"
        self._device_combo.setCurrentText(current)
        dev_row.addWidget(self._device_combo, 1)
        lay.addLayout(dev_row)

        self._chk_enabled = QCheckBox("Atalho global ativo")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.toggled.connect(self.enabled_toggled.emit)
        lay.addWidget(self._chk_enabled)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._btn_save = QPushButton("Aplicar e salvar")
        self._btn_save.clicked.connect(self._emit_settings)
        btn_row.addWidget(self._btn_save)
        lay.addLayout(btn_row)
        return frame

    def _build_footer(self) -> QLabel:
        footer = QLabel("Fechar esta janela mantém o app rodando na bandeja.")
        footer.setObjectName("footer")
        return footer

    # -------------------------------------------------------------- eventos

    def _emit_settings(self) -> None:
        self.settings_applied.emit({
            "hotkey": self._hotkey_edit.text().strip() or self.cfg.hotkey,
            "use_vision": self._chk_vision.isChecked(),
            "device": self._device_combo.currentText(),
        })

    # ------------------------------------------------------- API para o App

    def set_status(self, state: str, text: str, detail: str = "") -> None:
        color = _COLORS.get(state, _COLORS["idle"])
        self._status_dot.setStyleSheet(f"background:{color}; border-radius:7px;")
        self._status_text.setText(text)
        self._status_detail.setText(detail)
        self._status_detail.setVisible(bool(detail))
        # Sem OCR nem Ollama nao da para traduzir; o botao principal reflete isso.
        can = state not in ("error", "disabled")
        self._btn_translate.setEnabled(can or state == "loading")

    def set_health(self, health: Health) -> None:
        self._apply_component(self._ocr_dot, self._ocr_detail, health.ocr)
        self._apply_component(self._ollama_dot, self._ollama_detail, health.ollama)

    def _apply_component(self, dot: QLabel, detail: QLabel, comp: Component) -> None:
        color = {
            State.OK: _COLORS["ready"],
            State.MISSING: _COLORS["disabled"],
            State.ERROR: _COLORS["error"],
            State.UNKNOWN: _COLORS["disabled"],
        }[comp.state]
        dot.setStyleSheet(f"background:{color}; border-radius:6px;")
        detail.setText(comp.detail)

    def set_hotkey_label(self, label: str) -> None:
        self._hotkey_label = label
        self._btn_translate.setText(f"Traduzir uma área    {label}")

    # ------------------------------------------------------- fechar = esconder

    def request_real_close(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 (assinatura do Qt)
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()


def _demo() -> int:
    """Abre o painel isolado, com dados falsos, para inspecao visual."""
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    cfg = AppConfig()
    panel = ControlPanel(cfg, hotkey_label="Ctrl+Alt+Q")
    panel.set_status("ready", "Pronto", "OCR e modelo de tradução carregados")
    panel.set_health(Health(
        ocr=Component(State.OK, "paddleocr instalado"),
        ollama=Component(State.MISSING, "Ollama não respondeu"),
    ))
    panel.translate_requested.connect(lambda: print("traduzir"))
    panel.clear_requested.connect(lambda: print("limpar"))
    panel.settings_applied.connect(lambda d: print("settings", d))
    panel.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo())
