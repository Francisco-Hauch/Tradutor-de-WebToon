"""Gera uma pagina sintetica de webtoon para exercitar o pipeline.

Existe para que o projeto tenha um caso de teste reproduzivel e proprio, sem
depender de prints de obras de terceiros. Nao substitui as amostras reais em
`samples/` -- sao elas que definem o alvo de qualidade -- mas serve para
verificar que OCR, agrupamento e render estao de pe.

    uv run python tests/make_synthetic.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "samples" / "_synthetic.png"

# Frases genericas escritas para o teste; nenhuma vem de obra publicada.
BUBBLES = [
    ((60, 50, 340, 170), ["안녕하세요", "오랜만이에요"]),
    ((420, 90, 700, 240), ["이게 무슨", "일이야?", "설명해 줘"]),
    ((90, 300, 380, 430), ["나는 널", "믿었어"]),
    ((450, 360, 720, 480), ["빨리 도망쳐!"]),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for name in ("malgun.ttf", "malgunbd.ttf", "gulim.ttc", "batang.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise SystemExit("nenhuma fonte coreana encontrada (esperado 'Malgun Gothic' no Windows)")


def main() -> None:
    img = Image.new("RGB", (780, 540), (196, 200, 208))
    draw = ImageDraw.Draw(img)

    # Alguma textura de fundo, para o detector nao trabalhar num fundo liso.
    for i in range(0, 780, 40):
        draw.line([(i, 0), (i - 120, 540)], fill=(178, 183, 192), width=2)

    font = _font(30)
    for (x0, y0, x1, y1), lines in BUBBLES:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=28, fill=(255, 255, 255), outline=(20, 20, 20), width=3)
        total = len(lines) * 40
        cy = (y0 + y1) / 2 - total / 2
        for j, line in enumerate(lines):
            w = draw.textlength(line, font=font)
            draw.text(((x0 + x1) / 2 - w / 2, cy + j * 40), line, fill=(15, 15, 15), font=font)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT)
    print(f"amostra sintetica -> {OUT}")


if __name__ == "__main__":
    main()
