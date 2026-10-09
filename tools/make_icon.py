"""Gera o icone do app (PNG + ICO) so com primitivas do Pillow, sem fontes.

Roda uma vez e versiona a saida em `assets/`. Sem dependencia de fonte para
o resultado ser identico em qualquer maquina. Conceito: balao de fala (o app
fala por voce) com uma seta dupla dentro (traducao / troca de idioma), no azul
da identidade que ja existe no icone desenhado da bandeja.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

BLUE = (40, 120, 220, 255)
BLUE_DARK = (26, 92, 180, 255)
WHITE = (255, 255, 255, 255)

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def _rounded(draw: ImageDraw.ImageDraw, box, radius, fill) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 512.0

    # Fundo: quadrado arredondado com um leve degrade vertical (duas camadas).
    _rounded(d, (16 * s, 16 * s, 496 * s, 496 * s), 96 * s, BLUE_DARK)
    _rounded(d, (16 * s, 16 * s, 496 * s, 470 * s), 96 * s, BLUE)

    # Balao de fala branco.
    bubble = (96 * s, 120 * s, 416 * s, 336 * s)
    _rounded(d, bubble, 56 * s, WHITE)
    # Rabinho do balao (triangulo apontando para baixo-esquerda).
    d.polygon(
        [(176 * s, 330 * s), (176 * s, 410 * s), (248 * s, 330 * s)],
        fill=WHITE,
    )

    # Seta dupla dentro do balao: traducao / ida e volta entre idiomas.
    cy = 228 * s
    bar = 26 * s          # meia-altura das hastes
    left, right = 150 * s, 362 * s
    head = 46 * s         # largura da ponta

    # Haste superior, apontando para a direita.
    d.rectangle((left, cy - bar - 22 * s, right - head, cy - 22 * s + 4 * s), fill=BLUE)
    d.polygon(
        [(right - head, cy - bar - 22 * s - 16 * s),
         (right, cy - 22 * s - bar / 2 + 2 * s),
         (right - head, cy - 22 * s + 4 * s + 16 * s)],
        fill=BLUE,
    )
    # Haste inferior, apontando para a esquerda.
    d.rectangle((left + head, cy + 22 * s - 4 * s, right, cy + bar + 22 * s), fill=BLUE)
    d.polygon(
        [(left + head, cy + 22 * s - 4 * s - 16 * s),
         (left, cy + 22 * s + bar / 2 - 2 * s),
         (left + head, cy + bar + 22 * s + 16 * s)],
        fill=BLUE,
    )

    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = render(512)

    png = ASSETS / "icon.png"
    master.resize((256, 256), Image.LANCZOS).save(png)

    ico = ASSETS / "app.ico"
    master.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    print(f"gravado {png}")
    print(f"gravado {ico}")


if __name__ == "__main__":
    main()
