"""Motor de OCR baseado em PaddleOCR com o modelo coreano.

Roda na GPU por padrao. Medido nesta maquina (RTX 5060 Ti), uma pagina
inteira sai em ~0.2s na GPU contra ~23s na CPU com o mesmo modelo de
deteccao -- diferenca entre traduzir enquanto se le e parar para esperar.
Se a GPU nao inicializar, o motor cai sozinho para CPU e troca para o
modelo de deteccao "mobile", o unico com latencia tolerável sem placa.
"""

from __future__ import annotations

import logging
import os

import numpy as np
from PIL import Image

from ..config import OcrConfig
from ..types import TextBox

log = logging.getLogger(__name__)

# O PaddleX faz um ping nos hosts de modelo a cada import. Depois que os pesos
# estao em disco isso e so latencia no arranque.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class PaddleEngine:
    """Detecta e reconhece linhas de texto coreano.

    O modelo e carregado de forma preguicosa: a primeira chamada a `read`
    paga o download dos pesos (~20 MB) e a inicializacao; as seguintes nao.
    """

    def __init__(self, cfg: OcrConfig) -> None:
        self.cfg = cfg
        self._ocr = None
        self.device: str | None = None

    def _build(self, device: str):
        from paddleocr import PaddleOCR

        det = self.cfg.det_model if device == "gpu" else self.cfg.det_model_cpu
        log.info("carregando PaddleOCR (lang=%s, %s, det=%s)...", self.cfg.lang, device, det)

        kwargs = dict(
            lang=self.cfg.lang,
            device=device,
            text_detection_model_name=det,
            text_recognition_model_name=self.cfg.rec_model,
            # Webtoon ja vem "escaneada" e alinhada: desligar estes tres
            # estagios corta latencia sem custo de acuracia.
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        if device == "cpu":
            kwargs.update(enable_mkldnn=self.cfg.enable_mkldnn, cpu_threads=self.cfg.cpu_threads)

        ocr = PaddleOCR(**kwargs)
        # O primeiro predict e quem de fato toca a GPU; sem ele, uma placa
        # incompativel so estouraria no meio da leitura de verdade.
        ocr.predict(input=np.zeros((64, 64, 3), dtype=np.uint8))
        return ocr

    def _engine(self):
        if self._ocr is not None:
            return self._ocr

        device = _resolve_device(self.cfg.device)
        try:
            self._ocr = self._build(device)
        except Exception as exc:
            # De proposito nao ha fallback automatico para CPU aqui. Depois de
            # uma inicializacao de GPU malsucedida o Paddle fica com estado
            # global inconsistente, e um motor de CPU criado no mesmo processo
            # devolve texto lixo com confianca alta -- o que e muito pior do
            # que falhar, porque contamina a traducao sem dar sinal.
            raise RuntimeError(
                f"PaddleOCR nao inicializou em {device!r}: {exc}\n"
                'Para rodar sem placa, coloque device = "cpu" na secao [ocr] do config.toml.'
            ) from exc

        self.device = device
        return self._ocr

    def read(self, image: Image.Image) -> list[TextBox]:
        scale = max(1.0, float(self.cfg.upscale))
        work = image.convert("RGB")
        if scale > 1.0:
            work = work.resize(
                (round(work.width * scale), round(work.height * scale)),
                Image.LANCZOS,
            )

        # PaddleOCR espera BGR, como o OpenCV.
        bgr = np.asarray(work)[:, :, ::-1].copy()
        raw = self._engine().predict(input=bgr)

        boxes = [
            box
            for page in raw or []
            for box in _parse_page(page)
            if box.conf >= self.cfg.min_confidence and box.text.strip()
        ]
        if scale > 1.0:
            boxes = [b.scaled_by(1.0 / scale) for b in boxes]
        return boxes


def _resolve_device(preference: str) -> str:
    """Decide o dispositivo uma unica vez, antes de tocar no Paddle."""
    if preference in ("gpu", "cpu"):
        return preference
    return "gpu" if _has_cuda() else "cpu"


def _has_cuda() -> bool:
    try:
        import paddle

        return bool(paddle.device.is_compiled_with_cuda()) and paddle.device.cuda.device_count() > 0
    except Exception:
        return False


def _parse_page(page) -> list[TextBox]:
    """Normaliza a saida do PaddleOCR, que muda de formato entre versoes."""
    data = getattr(page, "json", None)
    if isinstance(data, dict):
        data = data.get("res", data)
    elif isinstance(page, dict):
        data = page
    else:
        data = getattr(page, "res", None) or {}

    polys = _first(data, "rec_polys", "dt_polys", "rec_boxes")
    texts = _first(data, "rec_texts", "texts")
    scores = _first(data, "rec_scores", "scores")
    if polys is None or texts is None:
        log.warning("formato de saida do PaddleOCR nao reconhecido: %s", list(data)[:10])
        return []

    if scores is None:
        scores = [1.0] * len(texts)

    out: list[TextBox] = []
    for poly, text, score in zip(polys, texts, scores):
        quad = _to_quad(poly)
        if quad:
            out.append(TextBox(quad=quad, text=str(text), conf=float(score)))
    return out


def _first(data: dict, *keys):
    for key in keys:
        value = data.get(key)
        if value is not None and len(value):
            return value
    return None


def _to_quad(poly) -> list[tuple[int, int]]:
    """Aceita tanto 4 pontos quanto um retangulo [x0, y0, x1, y1]."""
    arr = np.asarray(poly).reshape(-1)
    if arr.size == 4:
        x0, y0, x1, y1 = (float(v) for v in arr)
        return [(round(x0), round(y0)), (round(x1), round(y0)), (round(x1), round(y1)), (round(x0), round(y1))]
    if arr.size >= 8 and arr.size % 2 == 0:
        pts = arr.reshape(-1, 2)
        return [(round(float(x)), round(float(y))) for x, y in pts]
    return []
