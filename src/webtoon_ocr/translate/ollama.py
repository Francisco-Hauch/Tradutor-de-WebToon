"""Traducao via um LLM local servido pelo Ollama.

Roda offline e sem custo por chamada. A pagina inteira vai numa unica
requisicao, com as falas numeradas, e a resposta e forcada a um schema JSON
pelo proprio Ollama -- assim nao ha texto solto para adivinhar no parsing.
"""

from __future__ import annotations

import base64
import io
import json
import logging

import httpx
from PIL import Image

from ..config import CACHE_DIR, TranslateConfig
from .cache import TranslationCache

log = logging.getLogger(__name__)

# O modelo nao ganha nada com uma pagina em resolucao cheia, e imagem grande
# custa latencia. O texto continua legivel bem abaixo disso.
_MAX_IMAGE_SIDE = 1024

_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
            },
        }
    },
    "required": ["translations"],
}

_RULES = """Rules:
- Translate the meaning, not the words. Write how a native {lang} speaker would actually say it.
- Keep it colloquial. This is comic dialogue, not a document.
- The lines come from the same page and are in reading order, so use them as context for each other.
- Convey honorific and formality nuance through tone; do not add explanations or notes.
- Render sound effects as {lang} onomatopoeia.
- Keep each translation about as short as the original -- it has to fit inside the speech bubble.
- Return one entry per input id, keeping the ids exactly as given."""

_SYSTEM = """You translate Korean webtoon dialogue into {lang}.

"""

_TEXT_ONLY = (
    _SYSTEM
    + _RULES
    + """
- The lines come from OCR and the spaces between words are often missing. Read them as normal Korean.
- If a line is garbled beyond recognition, translate what you can rather than inventing names or events."""
)

# Com a imagem em maos o modelo pode CORRIGIR o OCR antes de traduzir, que e
# de longe o maior ganho de qualidade -- uma unica silaba lida errado ja faz
# o tradutor inventar um nome proprio que nunca existiu na pagina.
_WITH_IMAGE = (
    _SYSTEM
    + """You are given the page image AND the lines an OCR engine read from it.
The OCR is unreliable on stylized comic lettering: it drops the spaces between
words and misreads individual syllables.

Before translating, read the Korean in the IMAGE and use it to fix each line.
The image is the source of truth; the OCR text is only a hint. Never invent a
name, a person or an event to explain a syllable you cannot read -- if it stays
unreadable, translate only what is legible.

"""
    + _RULES
)


class OllamaTranslator:
    def __init__(self, cfg: TranslateConfig) -> None:
        self.cfg = cfg
        self._cache = TranslationCache(CACHE_DIR / "translations.sqlite3") if cfg.use_cache else None

    def translate(self, texts: list[str], image: Image.Image | None = None) -> list[str]:
        use_vision = bool(self.cfg.use_vision and image is not None)
        results: list[str | None] = [None] * len(texts)

        # O cache e por fala. Reler o capitulo, ou repetir o mesmo recorte
        # depois de rolar a pagina, nao chama o modelo de novo. O modo entra
        # na chave porque a traducao com imagem pode divergir da sem imagem;
        # a imagem em si nao entra, senao o cache nunca acertaria -- dois
        # recortes do mesmo balao quase nunca sao byte a byte iguais.
        mode = f"{self.cfg.target_lang}/{'vision' if use_vision else 'text'}"

        pending: list[int] = []
        for i, text in enumerate(texts):
            if not text.strip():
                results[i] = ""
                continue
            cached = self._cache.get(text, self.cfg.model, mode) if self._cache else None
            if cached is not None:
                results[i] = cached
            else:
                pending.append(i)

        if pending:
            fresh = self._request([texts[i] for i in pending], image if use_vision else None)
            for i, translated in zip(pending, fresh):
                results[i] = translated
                if self._cache and translated:
                    self._cache.put(texts[i], self.cfg.model, mode, translated)

        return [r if r is not None else "" for r in results]

    def _request(self, texts: list[str], image: Image.Image | None) -> list[str]:
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts))
        if image is not None:
            system = _WITH_IMAGE.format(lang=self.cfg.target_lang)
            prompt = (
                f"The OCR read these {len(texts)} lines from the page shown. "
                f"Correct them against the image, then translate:\n\n{numbered}"
            )
        else:
            system = _TEXT_ONLY.format(lang=self.cfg.target_lang)
            prompt = f"Translate these {len(texts)} lines:\n\n{numbered}"

        user: dict = {"role": "user", "content": prompt}
        if image is not None:
            user["images"] = [_encode(image)]

        payload = {
            "model": self.cfg.model,
            "messages": [{"role": "system", "content": system}, user],
            "stream": False,
            "format": _SCHEMA,
            "keep_alive": self.cfg.keep_alive,
            # Traducao quer fidelidade, nao criatividade.
            "options": {"temperature": 0.2},
        }

        try:
            resp = httpx.post(
                f"{self.cfg.host}/api/chat",
                json=payload,
                timeout=self.cfg.timeout_s,
            )
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise RuntimeError(
                f"Ollama nao respondeu em {self.cfg.host}. Verifique se o servico esta rodando "
                "(o instalador do Windows sobe junto com a sessao; se preciso, execute `ollama serve`)."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200]
            if exc.response.status_code == 404:
                raise RuntimeError(
                    f"Ollama nao encontrou o modelo {self.cfg.model!r}. Baixe com "
                    f"`ollama pull {self.cfg.model}`."
                ) from exc
            raise RuntimeError(f"Ollama devolveu HTTP {exc.response.status_code}: {detail}") from exc

        content = resp.json()["message"]["content"]
        return _parse(content, len(texts))


def _encode(image: Image.Image) -> str:
    """PNG em base64, reduzido, como o Ollama espera receber imagens."""
    rgb = image.convert("RGB")
    longest = max(rgb.width, rgb.height)
    if longest > _MAX_IMAGE_SIDE:
        scale = _MAX_IMAGE_SIDE / longest
        rgb = rgb.resize((max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))), Image.LANCZOS)

    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _parse(content: str, expected: int) -> list[str]:
    """Le a resposta e devolve exatamente `expected` itens, na ordem dos ids."""
    try:
        entries = json.loads(content)["translations"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"resposta do Ollama nao seguiu o schema pedido: {content[:200]}") from exc

    by_id: dict[int, str] = {}
    for entry in entries:
        try:
            by_id[int(entry["id"])] = str(entry["text"])
        except (KeyError, TypeError, ValueError):
            continue

    missing = [i for i in range(expected) if i not in by_id]
    if missing:
        # Preferimos deixar o balao sem traducao a deslocar as demais falas,
        # que e o que aconteceria se a lista fosse remontada por posicao.
        log.warning("modelo nao devolveu traducao para os ids %s", missing)

    return [by_id.get(i, "") for i in range(expected)]
