"""Contrato dos tradutores.

A interface recebe a LISTA de falas de uma vez, e nao uma fala por chamada.
Isso e proposital: o modelo vendo a pagina inteira acerta quem fala com quem,
continuidade de giria e pronome. Traduzir balao a balao perde esse contexto,
alem de multiplicar a latencia.
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image


class Translator(Protocol):
    def translate(self, texts: list[str], image: Image.Image | None = None) -> list[str]:
        """Devolve uma traducao por entrada, na mesma ordem e no mesmo tamanho.

        `image` e o recorte de onde as falas sairam. Tradutores multimodais
        usam para corrigir erros de OCR olhando o texto original; os demais
        ignoram.
        """
        ...
