"""Configuracao do app, lida de `config.toml` na raiz do projeto.

Tudo tem default sensato, entao o `config.toml` e opcional -- ele so existe
para voce ajustar modelo, atalho e motor de OCR sem mexer no codigo.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

# Onde vivem config.toml e o cache. Em dev, na raiz do repo. Dentro do
# executavel do PyInstaller (`sys.frozen`), ao lado do .exe -- senao cairiam
# na pasta temporaria que o onefile extrai e some ao fechar, e o "Aplicar e
# salvar" do painel nao persistiria nada.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "config.toml"
CACHE_DIR = PROJECT_ROOT / "cache"


@dataclass
class OcrConfig:
    engine: str = "paddle"  # "paddle" | "easyocr"
    lang: str = "korean"
    device: str = "auto"  # "auto" | "gpu" | "cpu"
    # O modelo "server" de deteccao acha mais linhas que o "mobile" e, na GPU,
    # custa uma pagina inteira em ~0.2s. Em CPU ele e inviavel (~23s), por isso
    # o fallback para CPU troca automaticamente para o "mobile".
    det_model: str = "PP-OCRv5_server_det"
    det_model_cpu: str = "PP-OCRv5_mobile_det"
    # Precisa ser nomeado explicitamente. Deixar o PaddleOCR deduzir o modelo
    # de reconhecimento a partir de `lang` faz o reconhecimento devolver
    # strings VAZIAS na GPU -- sem erro, so texto em branco. Nomeando o modelo,
    # a mesma GPU le as linhas corretamente.
    rec_model: str = "korean_PP-OCRv5_mobile_rec"
    # Texto de webtoon em zoom 100% e pequeno demais para o modelo. Ampliar
    # antes de reconhecer e o maior ganho isolado de acuracia do pipeline.
    upscale: float = 2.0
    min_confidence: float = 0.5
    # Só se aplica ao fallback de CPU. O backend oneDNN do PaddlePaddle 3.3
    # quebra no executor PIR com "ConvertPirAttribute2RuntimeAttribute not
    # support", entao fica desligado -- o executor padrao roda sem o bug.
    enable_mkldnn: bool = False
    cpu_threads: int = 8


@dataclass
class TranslateConfig:
    provider: str = "ollama"
    model: str = "gemma3:12b"
    host: str = "http://127.0.0.1:11434"
    target_lang: str = "English"
    timeout_s: float = 120.0
    use_cache: bool = True
    # Por padrao o Ollama descarrega o modelo da VRAM depois de 5 min ociosos,
    # e recarregar custa ~80s. Numa sessao de leitura isso cairia bem no meio
    # do capitulo, entao mantemos o modelo residente por bem mais tempo.
    keep_alive: str = "30m"
    # Manda o recorte junto do texto para o modelo, que e multimodal, corrigir
    # o que o OCR leu errado antes de traduzir. Fonte estilizada de webtoon
    # erra bastante, e sem isso o erro vira conteudo inventado: um "젠장"
    # (droga) lido como "렌장" virou o nome proprio "Len" numa fala real.
    use_vision: bool = True


@dataclass
class RenderConfig:
    font_family: str = "Segoe UI"
    min_font_pt: int = 8
    max_font_pt: int = 40
    box_padding: int = 6
    corner_radius: int = 8


@dataclass
class AppConfig:
    hotkey: str = "<ctrl>+<alt>+q"
    ocr: OcrConfig = field(default_factory=OcrConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    render: RenderConfig = field(default_factory=RenderConfig)


def _apply(target, data: dict) -> None:
    """Copia do dict apenas as chaves que existem na dataclass, ignorando o resto."""
    known = {f.name for f in fields(target)}
    for key, value in data.items():
        if key in known and not isinstance(getattr(target, key), (OcrConfig, TranslateConfig, RenderConfig)):
            setattr(target, key, value)


def load_config(path: Path | None = None) -> AppConfig:
    cfg = AppConfig()
    path = path or CONFIG_PATH
    if not path.exists():
        return cfg

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    _apply(cfg, data)
    for section, obj in (("ocr", cfg.ocr), ("translate", cfg.translate), ("render", cfg.render)):
        if isinstance(data.get(section), dict):
            _apply(obj, data[section])
    return cfg


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    """Grava a config inteira em TOML, com as tres secoes.

    Existe para o painel persistir o que o usuario mexe (atalho, use_vision,
    device) sem depender de um escritor de TOML externo. Serializa apenas os
    campos das dataclasses, entao o arquivo fica sempre valido para o
    `load_config` reler.
    """
    path = path or CONFIG_PATH
    lines: list[str] = [
        "# Gerado pelo painel do Tradutor de Webtoon.",
        "# Todo campo e opcional; apagar um volta ao default do codigo.",
        "",
        f"hotkey = {_toml_value(cfg.hotkey)}",
    ]
    for section, obj in (("ocr", cfg.ocr), ("translate", cfg.translate), ("render", cfg.render)):
        lines.append("")
        lines.append(f"[{section}]")
        for f in fields(obj):
            lines.append(f"{f.name} = {_toml_value(getattr(obj, f.name))}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
