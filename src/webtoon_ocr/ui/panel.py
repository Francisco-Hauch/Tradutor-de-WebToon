"""A cara do app: um dashboard com o estado, as metricas e os ajustes.

Layout: cabecalho (titulo, estado, botoes) + abas *Painel* / *Historico* /
*Ajustes* a esquerda, e a lista das ultimas traducoes (coreano -> ingles) na
lateral direita. Abre ocupando ~65% da tela.

Nao conhece o App diretamente: fala por sinais Qt (para o App conectar) e
recebe estado por `set_status`/`set_health`/`set_metrics`. Assim da para
abri-lo isolado para inspecao visual, sem bandeja, sem OCR e sem rede:
`python -m webtoon_ocr.ui.panel`.

Fechar a janela NAO fecha o app: esconde para a bandeja. Sair de verdade so
pelo botao da bandeja ou pelo "Sair" da aba Ajustes.
"""

from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..assets import app_icon
from ..config import AppConfig
from ..health import Component, Health, State
from ..metricas import Metrics

# Paleta: azul-escuro pastel de base, cinza para fonte, bordas e badges.
BG = "#232F45"
CARD = "#2C3A54"
BADGE = "#3A4760"
BORDER = "#5A6880"
TEXT = "#DDE3EC"
MUTED = "#98A3B3"
ACCENT = "#9DB8E3"
ACCENT_HOVER = "#B5CAEC"
ACCENT_TEXT = "#1B2538"
OCR_LINE = "#9DB8E3"
TRAD_LINE = "#E3C39D"

# Cores de estado, reaproveitadas pelo ponto de status e pelos indicadores.
_COLORS = {
    "loading": "#E7C27D",
    "ready": "#8CCB9B",
    "error": "#E89393",
    "idle": ACCENT,
    "disabled": "#7D8796",
}

_STYLE = f"""
QWidget#panel {{ background: {BG}; }}
QLabel {{ color: {TEXT}; }}
QLabel#title {{ font-size: 20px; font-weight: 600; }}
QLabel#subtitle, QLabel#statusDetail, QLabel#footer {{ color: {MUTED}; font-size: 12px; }}
QLabel#statusText {{ font-size: 13px; font-weight: 600; }}
QLabel#sectionLabel {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel#kpiValue {{ font-size: 26px; font-weight: 600; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#badge {{ background: {BADGE}; border: 1px solid {BORDER}; border-radius: 14px; }}

QPushButton {{
    background: {BADGE}; color: {TEXT};
    border: 2px solid {BORDER}; border-radius: 9px;
    padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #46546E; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #2F3B52; }}
QPushButton:disabled {{ color: #6D7889; border-color: #44506A; background: #2E3A50; }}
QPushButton#primary {{
    background: {ACCENT}; color: {ACCENT_TEXT};
    border: 2px solid #C9D8F0; font-weight: 600; font-size: 14px; padding: 9px 18px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; border-color: #FFFFFF; }}
QPushButton#primary:pressed {{ background: #86A3D2; }}
QPushButton#primary:disabled {{ background: #55688A; color: #2E3A50; border-color: #55688A; }}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {MUTED};
    padding: 8px 18px; margin-right: 6px; font-size: 13px; font-weight: 600;
    border: 2px solid transparent; border-radius: 9px;
}}
QTabBar::tab:hover {{ color: {TEXT}; border-color: {BORDER}; }}
QTabBar::tab:selected {{ color: {TEXT}; background: {BADGE}; border-color: {BORDER}; }}

QLineEdit, QComboBox {{
    background: {BADGE}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 8px; font-size: 13px;
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; color: {TEXT}; selection-background-color: {BADGE}; }}
QCheckBox {{ color: {TEXT}; font-size: 13px; }}

QListWidget, QTableWidget {{
    background: transparent; color: {TEXT}; border: none; font-size: 13px;
    gridline-color: {BADGE};
}}
QListWidget::item {{ padding: 6px 2px; border-bottom: 1px solid {BADGE}; }}
QHeaderView::section {{
    background: {BADGE}; color: {MUTED}; border: none; padding: 6px; font-weight: 600;
}}
"""


def _shadow(widget: QWidget, blur: int = 16, dy: int = 3) -> QWidget:
    # O QSS nao tem box-shadow; a sombra vem de um efeito grafico.
    fx = QGraphicsDropShadowEffect(widget)
    fx.setBlurRadius(blur)
    fx.setOffset(0, dy)
    fx.setColor(QColor(0, 0, 0, 120))
    widget.setGraphicsEffect(fx)
    return widget


def _button(text: str, primary: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        btn.setObjectName("primary")
    _shadow(btn, 14, 2)
    return btn


def _dot(color: str, size: int = 12) -> QLabel:
    dot = QLabel()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"background:{color}; border-radius:{size // 2}px;")
    return dot


def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionLabel")
    return label


def _card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    if title:
        lay.addWidget(_section(title))
    _shadow(frame, 22, 4)
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
        self.setMinimumSize(1000, 660)
        self._size_to_screen(0.65)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(16)

        main = QVBoxLayout()
        main.setSpacing(14)
        main.addLayout(self._build_header())
        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard(), "Painel")
        tabs.addTab(self._build_history(), "Histórico")
        tabs.addTab(self._build_settings(), "Ajustes")
        tabs.setCornerWidget(self._build_status_badge(), Qt.Corner.TopRightCorner)
        main.addWidget(tabs, 1)
        root.addLayout(main, 1)
        root.addWidget(self._build_sidebar())

    def _size_to_screen(self, frac: float) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        w = max(self.minimumWidth(), int(geo.width() * frac))
        h = max(self.minimumHeight(), int(geo.height() * frac))
        self.setGeometry(geo.x() + (geo.width() - w) // 2, geo.y() + (geo.height() - h) // 2, w, h)

    # -------------------------------------------------------------- cabecalho

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

        self._btn_clear = _button("Limpar (Esc)")
        self._btn_clear.clicked.connect(self.clear_requested.emit)
        row.addWidget(self._btn_clear)

        self._btn_translate = _button(f"Traduzir uma área  ·  {self._hotkey_label}", primary=True)
        self._btn_translate.clicked.connect(self.translate_requested.emit)
        row.addWidget(self._btn_translate)
        return row

    def _build_status_badge(self) -> QFrame:
        badge = QFrame()
        badge.setObjectName("badge")
        lay = QHBoxLayout(badge)
        lay.setContentsMargins(12, 5, 14, 5)
        lay.setSpacing(8)
        self._status_dot = _dot(_COLORS["idle"], 10)
        lay.addWidget(self._status_dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self._status_text = QLabel("Iniciando…")
        self._status_text.setObjectName("statusText")
        lay.addWidget(self._status_text)
        self._status_detail = QLabel("")
        self._status_detail.setObjectName("statusDetail")
        lay.addWidget(self._status_detail)
        return badge

    # -------------------------------------------------------------- aba Painel

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(14)

        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        self._kpi = {}
        for key, label in (
            ("recortes", "RECORTES"),
            ("baloes", "BALÕES TRADUZIDOS"),
            ("ultimo", "ÚLTIMO RECORTE"),
            ("media", "MÉDIA POR RECORTE"),
        ):
            frame, card = _card(label)
            value = QLabel("—")
            value.setObjectName("kpiValue")
            card.addWidget(value)
            self._kpi[key] = value
            kpis.addWidget(frame)
        lay.addLayout(kpis)

        lay.addWidget(self._build_chart_card(), 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        frame, card = _card("PALAVRAS QUE MAIS APARECEM")
        self._top_list = QListWidget()
        self._top_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        card.addWidget(self._top_list)
        bottom.addWidget(frame, 1)
        bottom.addWidget(self._build_health_card(), 1)
        lay.addLayout(bottom, 1)
        return page

    def _build_chart_card(self) -> QFrame:
        frame, card = _card("TEMPO POR RECORTE (ms) — ÚLTIMOS 50")
        self._series_ocr = QLineSeries(name="OCR")
        self._series_trad = QLineSeries(name="Tradução")
        for series, color in ((self._series_ocr, OCR_LINE), (self._series_trad, TRAD_LINE)):
            series.setPen(QPen(QColor(color), 2.5))

        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.setPlotAreaBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        chart.legend().setLabelColor(QColor(TEXT))
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignTop)
        chart.addSeries(self._series_ocr)
        chart.addSeries(self._series_trad)

        self._axis_x = QValueAxis()
        self._axis_x.setLabelFormat("%d")
        self._axis_y = QValueAxis()
        self._axis_y.setLabelFormat("%d")
        for axis, align in ((self._axis_x, Qt.AlignmentFlag.AlignBottom), (self._axis_y, Qt.AlignmentFlag.AlignLeft)):
            axis.setLabelsColor(QColor(MUTED))
            axis.setGridLineColor(QColor(BADGE))
            axis.setLinePenColor(QColor(BORDER))
            chart.addAxis(axis, align)
            self._series_ocr.attachAxis(axis)
            self._series_trad.attachAxis(axis)

        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setStyleSheet("background: transparent;")
        view.setMinimumHeight(180)
        card.addWidget(view, 1)
        return frame

    def _build_health_card(self) -> QFrame:
        frame, lay = _card("DEPENDÊNCIAS")

        self._ocr_dot = _dot(_COLORS["disabled"])
        self._ocr_detail = QLabel("verificando…")
        self._ocr_detail.setObjectName("statusDetail")
        lay.addLayout(self._health_row(self._ocr_dot, "OCR (PaddleOCR)", self._ocr_detail))

        self._ollama_dot = _dot(_COLORS["disabled"])
        self._ollama_detail = QLabel("verificando…")
        self._ollama_detail.setObjectName("statusDetail")
        lay.addLayout(self._health_row(self._ollama_dot, "Tradução (Ollama)", self._ollama_detail))
        lay.addStretch(1)
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

    # -------------------------------------------------------------- aba Historico

    def _build_history(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 0, 0)
        frame, card = _card("TODAS AS TRADUÇÕES (MAIS RECENTES PRIMEIRO)")
        self._history = QTableWidget(0, 2)
        self._history.setHorizontalHeaderLabels(["Coreano", "Inglês"])
        self._history.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._history.verticalHeader().setVisible(False)
        self._history.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._history.setWordWrap(True)
        card.addWidget(self._history)
        lay.addWidget(frame)
        return page

    # -------------------------------------------------------------- aba Ajustes

    def _build_settings(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 12, 0, 0)
        frame, lay = _card("AJUSTES")

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Atalho"), 0, 0)
        self._hotkey_edit = QLineEdit(self.cfg.hotkey)
        self._hotkey_edit.setPlaceholderText("<ctrl>+<alt>+q")
        grid.addWidget(self._hotkey_edit, 0, 1)

        grid.addWidget(QLabel("Dispositivo do OCR"), 1, 0)
        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "gpu", "cpu"])
        current = self.cfg.ocr.device if self.cfg.ocr.device in ("auto", "gpu", "cpu") else "auto"
        self._device_combo.setCurrentText(current)
        grid.addWidget(self._device_combo, 1, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        self._chk_vision = QCheckBox("Corrigir o OCR pela imagem antes de traduzir (use_vision)")
        self._chk_vision.setChecked(self.cfg.translate.use_vision)
        lay.addWidget(self._chk_vision)

        self._chk_enabled = QCheckBox("Atalho global ativo")
        self._chk_enabled.setChecked(True)
        self._chk_enabled.toggled.connect(self.enabled_toggled.emit)
        lay.addWidget(self._chk_enabled)

        btn_row = QHBoxLayout()
        btn_quit = _button("Sair do app")
        btn_quit.clicked.connect(self.quit_requested.emit)
        btn_row.addWidget(btn_quit)
        btn_row.addStretch(1)
        self._btn_save = _button("Aplicar e salvar", primary=True)
        self._btn_save.clicked.connect(self._emit_settings)
        btn_row.addWidget(self._btn_save)
        lay.addLayout(btn_row)

        outer.addWidget(frame)
        footer = QLabel("Fechar esta janela mantém o app rodando na bandeja.")
        footer.setObjectName("footer")
        outer.addWidget(footer)
        outer.addStretch(1)
        return page

    # -------------------------------------------------------------- lateral

    def _build_sidebar(self) -> QFrame:
        frame, lay = _card("ÚLTIMAS PALAVRAS")
        frame.setFixedWidth(300)
        self._recent_list = QListWidget()
        self._recent_list.setWordWrap(True)
        self._recent_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        lay.addWidget(self._recent_list, 1)
        return frame

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
        self._status_dot.setStyleSheet(f"background:{color}; border-radius:5px;")
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

    def set_metrics(self, metrics: Metrics) -> None:
        d = metrics.data
        totals = [t["ocr_ms"] + t["traducao_ms"] for t in d["tempos"]]
        self._kpi["recortes"].setText(f"{d['recortes']:,}".replace(",", "."))
        self._kpi["baloes"].setText(f"{d['baloes']:,}".replace(",", "."))
        self._kpi["ultimo"].setText(f"{totals[-1]:,} ms".replace(",", ".") if totals else "—")
        self._kpi["media"].setText(f"{sum(totals) // len(totals):,} ms".replace(",", ".") if totals else "—")

        self._series_ocr.replace([QPointF(i, t["ocr_ms"]) for i, t in enumerate(d["tempos"], 1)])
        self._series_trad.replace([QPointF(i, t["traducao_ms"]) for i, t in enumerate(d["tempos"], 1)])
        self._axis_x.setRange(1, max(2, len(totals)))
        self._axis_y.setRange(0, max([*totals, 100]) * 1.1)
        self._axis_y.applyNiceNumbers()

        self._top_list.clear()
        for word, n in metrics.top_palavras(10):
            self._top_list.addItem(f"{word}    ×{n}")

        recentes = d["recentes"]
        self._recent_list.clear()
        for r in recentes[:30]:
            self._recent_list.addItem(f"{r['ko']}\n→ {r['en']}")

        self._history.setRowCount(len(recentes))
        for row, r in enumerate(recentes):
            self._history.setItem(row, 0, QTableWidgetItem(r["ko"]))
            self._history.setItem(row, 1, QTableWidgetItem(r["en"]))
        self._history.resizeRowsToContents()

    def set_hotkey_label(self, label: str) -> None:
        self._hotkey_label = label
        self._btn_translate.setText(f"Traduzir uma área  ·  {label}")

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
    import random
    import sys
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication

    from ..types import Block

    app = QApplication.instance() or QApplication(sys.argv)
    metrics = Metrics(Path(tempfile.mkdtemp()) / "metricas.json")
    falas = [("사랑해", "I love you"), ("어디 가?", "Where are you going?"), ("괜찮아, 사랑해", "It's okay, I love you")]
    for _ in range(24):
        ko, en = random.choice(falas)
        metrics.record(random.randint(600, 1100), random.randint(1500, 3200),
                       [Block(rect=(0, 0, 1, 1), source=ko, translated=en)])

    panel = ControlPanel(AppConfig(), hotkey_label="Ctrl+Alt+Q")
    panel.set_status("ready", "Pronto", "OCR e modelo carregados")
    panel.set_health(Health(
        ocr=Component(State.OK, "paddleocr instalado"),
        ollama=Component(State.MISSING, "Ollama não respondeu"),
    ))
    panel.set_metrics(metrics)
    panel.translate_requested.connect(lambda: print("traduzir"))
    panel.clear_requested.connect(lambda: print("limpar"))
    panel.settings_applied.connect(lambda d: print("settings", d))
    panel.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(_demo())
