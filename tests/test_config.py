"""save_config -> load_config tem que ser um round-trip fiel.

O painel grava a config quando o usuario mexe nos ajustes; se o arquivo
gerado nao reabrir igual, o ajuste se perde silenciosamente na proxima vez.
"""

from __future__ import annotations

from webtoon_ocr.config import AppConfig, load_config, save_config


def test_round_trip_defaults(tmp_path):
    path = tmp_path / "config.toml"
    save_config(AppConfig(), path)
    reloaded = load_config(path)

    original = AppConfig()
    assert reloaded.hotkey == original.hotkey
    assert reloaded.ocr.device == original.ocr.device
    assert reloaded.translate.use_vision == original.translate.use_vision
    assert reloaded.render.font_family == original.render.font_family


def test_round_trip_modified(tmp_path):
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.hotkey = "<ctrl>+<alt>+w"
    cfg.ocr.device = "cpu"
    cfg.translate.use_vision = False
    cfg.translate.timeout_s = 90.0
    save_config(cfg, path)

    reloaded = load_config(path)
    assert reloaded.hotkey == "<ctrl>+<alt>+w"
    assert reloaded.ocr.device == "cpu"
    assert reloaded.translate.use_vision is False
    assert reloaded.translate.timeout_s == 90.0


def test_string_escaping(tmp_path):
    path = tmp_path / "config.toml"
    cfg = AppConfig()
    cfg.render.font_family = 'Fonte "estranha"'
    save_config(cfg, path)

    reloaded = load_config(path)
    assert reloaded.render.font_family == 'Fonte "estranha"'
