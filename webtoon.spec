# -*- mode: python ; coding: utf-8 -*-
"""Receita do executavel leve do Tradutor de Webtoon.

Este build empacota SO a casca do app: a janela, a bandeja, a captura e o
overlay. A stack pesada de OCR (PaddlePaddle + CUDA, varios GB) e o cliente de
traducao ficam DE FORA -- o app sobe, mostra a cara e roda na bandeja sem
Ollama nem placa. Quando essas dependencias existem na maquina, o pipeline as
importa em tempo de execucao; num .exe leve, o painel so mostra que estao
ausentes.

Construa numa venv que tenha apenas as dependencias leves (veja
`requirements-app.txt`) -- assim o PyInstaller nao tem como arrastar Paddle.
Os `excludes` abaixo sao um cinto de seguranca a mais.

    pyinstaller webtoon.spec        # gera dist/Tradutor de Webtoon.exe
"""

block_cipher = None

# Sao pesados/irrelevantes para a casca; ficam de fora explicitamente para o
# build nao inchar nem tentar resolver import opcional que nao instalamos.
EXCLUDES = [
    "paddle", "paddleocr", "paddlex", "easyocr",
    "cv2", "opencv-python", "scipy", "sklearn", "skimage",
    "matplotlib", "pandas", "torch", "torchvision", "tensorflow",
    "IPython", "notebook",
]

# Backends que o PyInstaller as vezes nao descobre sozinho no onefile.
HIDDEN = [
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "mss.windows",
]

a = Analysis(
    ["run_app.py"],
    pathex=["src"],
    binaries=[],
    datas=[("assets", "assets")],  # icone e afins vao para <bundle>/assets
    hiddenimports=HIDDEN,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Tradutor de Webtoon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # app de janela/bandeja, sem console preto
    disable_windowed_traceback=False,
    icon="assets/app.ico",
)
