"""Entrada de linha de comando -- a bancada de desenvolvimento do projeto.

Cada fase do plano ganha um subcomando aqui, para poder ser exercitada
isolada e sem interface grafica:

    wt ocr        samples/page1.png --debug-out out/page1_boxes.png
    wt translate  samples/page1.png -o out/page1_en.png
    wt snip
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from PIL import Image

from .config import load_config


def _force_utf8_console() -> None:
    """Faz o console aguentar hangul.

    O terminal do Windows entrega stdout em cp1252, que nao tem hangul: um
    `print` do texto lido pelo OCR levanta UnicodeEncodeError e derruba o
    comando ANTES de salvar a imagem traduzida. `errors="replace"` cobre o
    caso do console realmente nao conseguir desenhar o glifo -- ai sai '?'
    na tela, mas o comando termina e o PNG e gravado.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # O PaddleX e barulhento demais no nivel INFO.
    logging.getLogger("paddlex").setLevel(logging.WARNING)
    logging.getLogger("paddle").setLevel(logging.WARNING)


def cmd_ocr(args: argparse.Namespace) -> int:
    from .debug import draw_boxes
    from .ocr import build_engine

    cfg = load_config()
    if args.upscale is not None:
        cfg.ocr.upscale = args.upscale

    image = Image.open(args.image)
    engine = build_engine(cfg.ocr)

    started = time.perf_counter()
    boxes = engine.read(image)
    elapsed = time.perf_counter() - started

    print(f"\n{len(boxes)} linha(s) em {elapsed:.2f}s  (upscale {cfg.ocr.upscale}x)\n")
    for i, box in enumerate(boxes):
        x, y, w, h = box.rect
        print(f"[{i:2d}] conf={box.conf:.2f}  ({x:4d},{y:4d}) {w:3d}x{h:3d}  {box.text}")

    if args.debug_out:
        out = Path(args.debug_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        draw_boxes(image, boxes).save(out)
        print(f"\nimagem de debug -> {out}")

    return 0 if boxes else 1


def cmd_translate(args: argparse.Namespace) -> int:
    from .debug import draw_boxes
    from .pipeline import build
    from .render.compose import compose

    cfg = load_config()
    image = Image.open(args.image)

    started = time.perf_counter()
    blocks = build(cfg).run(image)
    elapsed = time.perf_counter() - started

    print(f"\n{len(blocks)} balao(oes) em {elapsed:.2f}s\n")
    for i, block in enumerate(blocks):
        print(f"[{i:2d}] {block.source}")
        print(f"     -> {block.translated}")

    if not blocks:
        return 1

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    compose(image, blocks, cfg.render).save(out)
    print(f"\ntraduzida -> {out}")

    if args.debug_out:
        dbg = Path(args.debug_out)
        dbg.parent.mkdir(parents=True, exist_ok=True)
        lines = [ln for b in blocks for ln in b.lines]
        draw_boxes(image, lines, blocks).save(dbg)
        print(f"debug     -> {dbg}")

    return 0


def cmd_snip(args: argparse.Namespace) -> int:
    from . import capture
    from .selector import select_region

    print("arraste um retangulo sobre a area a traduzir (Esc ou botao direito cancela)")
    screen = capture.grab()
    rect = select_region(screen)
    if rect is None:
        print("cancelado")
        return 1

    x, y, w, h = rect
    print(f"selecionado: {w}x{h} em ({x},{y})  [coords do desktop virtual]")

    # Recorta do quadro ja congelado em vez de capturar de novo: o conteudo
    # pode ter rolado desde entao, e a area lida tem que ser a que voce viu.
    ox, oy, _, _ = capture.virtual_screen()
    crop = screen.crop((x - ox, y - oy, x - ox + w, y - oy + h))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out)
    print(f"recorte -> {out}")

    if args.translate:
        from .pipeline import build
        from .render.compose import compose

        cfg = load_config()
        blocks = build(cfg).run(crop)
        for block in blocks:
            print(f"  {block.source}\n    -> {block.translated}")
        if blocks:
            translated_path = out.with_name(f"{out.stem}_en{out.suffix}")
            compose(crop, blocks, cfg.render).save(translated_path)
            print(f"traduzido -> {translated_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wt", description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ocr = sub.add_parser("ocr", help="le o texto coreano de uma imagem")
    p_ocr.add_argument("image", type=Path)
    p_ocr.add_argument("--debug-out", type=Path, help="salva a imagem com as caixas desenhadas")
    p_ocr.add_argument("--upscale", type=float, help="sobrepoe o upscale da config")
    p_ocr.set_defaults(func=cmd_ocr)

    p_tr = sub.add_parser("translate", help="le, traduz e desenha a traducao por cima")
    p_tr.add_argument("image", type=Path)
    p_tr.add_argument("-o", "--output", type=Path, required=True)
    p_tr.add_argument("--debug-out", type=Path, help="salva tambem a imagem com linhas e baloes marcados")
    p_tr.set_defaults(func=cmd_translate)

    p_snip = sub.add_parser("snip", help="congela a tela e recorta uma area arrastando")
    p_snip.add_argument("-o", "--output", type=Path, default=Path("out/snip.png"))
    p_snip.add_argument("--translate", action="store_true", help="ja traduz o recorte")
    p_snip.set_defaults(func=cmd_snip)

    p_run = sub.add_parser("run", help="sobe o app na bandeja com o atalho global")
    p_run.set_defaults(func=lambda _: __import__("webtoon_ocr.app", fromlist=["main"]).main())

    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
