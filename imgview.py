"""Imagens no terminal: renderizar, pegar da area de transferencia e de caminhos.

Modos de desenho:

* `half`   -- meio-blocos coloridos (2 pixels por celula). Padrao: usa so cores
              ANSI, nao escreve escape sequence nenhuma por fora do Rich e por
              isso convive em paz com a TUI;
* `blocks` -- um bloco cheio por pixel, para terminais que lidam mal com cor de
              fundo;
* `sixel` / `tgp` / `auto` -- imagem de verdade via `textual-image`.

Cuidado com os tres ultimos: a biblioteca precisa *sondar* o terminal (escreve
escape sequences no stdout e le a resposta no stdin) e isso tem que acontecer
ANTES do Textual assumir o stdin -- se rodar com a TUI no ar, a tela embaralha.
Por isso `preparar_graficos()` existe e e chamada antes de abrir a TUI, e os
modos graficos so ficam liberados se ela tiver rodado.
"""

from __future__ import annotations

import time
from pathlib import Path

from session_native import sistema
from session_native.i18n import t

MODOS = ("half", "blocks", "auto", "sixel", "tgp")
MODOS_GRAFICOS = ("auto", "sixel", "tgp")
_APELIDOS_MODO = {"meio": "half", "blocos": "blocks"}
LARGURA_PADRAO = 44  # em celulas do terminal
LARGURA_MIN, LARGURA_MAX = 4, 200
FUNDO_TRANSPARENCIA = (24, 24, 24)  # fundo assumido para imagens com alfa

EXTENSOES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".avif", ".ico")

_graficos_prontos = False


class ImagemError(RuntimeError):
    """Nao foi possivel ler, converter ou renderizar a imagem."""


def normalizar_modo(valor: str) -> str | None:
    """'meio' -> 'half', 'SIXEL' -> 'sixel'; None se nao for um modo."""
    modo = (valor or "").strip().lower()
    modo = _APELIDOS_MODO.get(modo, modo)
    return modo if modo in MODOS else None


def preparar_graficos() -> bool:
    """Sonda o terminal uma unica vez, antes de qualquer TUI assumir o stdin.

    Devolve True se os modos graficos (sixel/tgp) ficaram utilizaveis.
    """
    global _graficos_prontos
    if _graficos_prontos:
        return True
    try:
        from textual_image._terminal import probe_terminal

        probe_terminal()  # o resultado fica em cache para o resto do processo
        _graficos_prontos = True
    except Exception:
        _graficos_prontos = False
    return _graficos_prontos


def graficos_disponiveis() -> bool:
    return _graficos_prontos


def _abrir(caminho: str | Path):
    """Abre a imagem em RGB, achatando transparencia e paleta."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise ImagemError(t("file not found: {path}", path=arquivo))
    try:
        from PIL import Image as PILImage

        with PILImage.open(arquivo) as img:
            img.load()  # GIF animado: fica no primeiro quadro
            if img.mode in ("RGBA", "LA", "P"):
                rgba = img.convert("RGBA")
                fundo = PILImage.new("RGBA", rgba.size, (*FUNDO_TRANSPARENCIA, 255))
                return PILImage.alpha_composite(fundo, rgba).convert("RGB")
            return img.convert("RGB")
    except ImagemError:
        raise
    except Exception as exc:
        raise ImagemError(t("not a readable image: {error}", error=exc)) from exc


def _redimensionar(img, largura: int, *, dobrar_altura: bool):
    """Escala para `largura` celulas mantendo a proporcao.

    Com meio-blocos cada celula guarda 2 pixels na vertical e 1 na horizontal,
    o que ja compensa a celula do terminal ser ~2x mais alta que larga.
    """
    from PIL import Image as PILImage

    largura = max(LARGURA_MIN, min(LARGURA_MAX, int(largura)))
    proporcao = img.height / img.width if img.width else 1.0
    if dobrar_altura:
        altura_px = max(2, round(largura * proporcao))
        altura_px += altura_px % 2  # par: cada celula come 2 linhas
    else:
        altura_px = max(1, round(largura * proporcao / 2))
    return img.resize((largura, altura_px), PILImage.LANCZOS)


def _segmentos(img, *, meio: bool) -> list:
    """Converte os pixels em segmentos coloridos do Rich (sem tocar no terminal)."""
    from rich.color import Color
    from rich.color_triplet import ColorTriplet
    from rich.segment import Segment
    from rich.style import Style

    pixels = img.load()
    largura, altura = img.size
    quebra = Segment("\n")
    saida: list = []

    if meio:
        for y in range(0, altura - 1, 2):
            for x in range(largura):
                cima = Color.from_triplet(ColorTriplet(*pixels[x, y]))
                baixo = Color.from_triplet(ColorTriplet(*pixels[x, y + 1]))
                saida.append(Segment("▀", Style(color=cima, bgcolor=baixo)))
            saida.append(quebra)
    else:
        for y in range(altura):
            for x in range(largura):
                cor = Color.from_triplet(ColorTriplet(*pixels[x, y]))
                saida.append(Segment("█", Style(color=cor)))
            saida.append(quebra)
    return saida


def renderizar(caminho: str | Path, *, largura: int = LARGURA_PADRAO, modo: str = "half"):
    """Devolve um renderavel do Rich com a imagem (para escrever no log)."""
    modo = normalizar_modo(modo) or "half"
    if modo in MODOS_GRAFICOS:
        if not _graficos_prontos:
            raise ImagemError(
                t(
                    "the '{mode}' mode must probe the terminal before the interface opens; "
                    "reopen with --mode {mode}",
                    mode=modo,
                )
            )
        from textual_image import renderable

        classe = {
            "auto": renderable.Image,
            "sixel": renderable.SixelImage,
            "tgp": renderable.TGPImage,
        }[modo]
        try:
            return classe(_abrir(caminho), width=largura)
        except ImagemError:
            raise
        except Exception as exc:
            raise ImagemError(t("failed to render: {error}", error=exc)) from exc

    from rich.segment import Segments

    img = _redimensionar(_abrir(caminho), largura, dobrar_altura=modo != "blocks")
    try:
        return Segments(_segmentos(img, meio=modo != "blocks"))
    except Exception as exc:
        raise ImagemError(t("failed to draw: {error}", error=exc)) from exc


def dimensoes(caminho: str | Path) -> tuple[int, int] | None:
    try:
        from PIL import Image as PILImage

        with PILImage.open(caminho) as img:
            return img.width, img.height
    except Exception:
        return None


def _candidatos(texto: str) -> list[Path]:
    """Os caminhos que uma linha solta pode querer dizer.

    Terminais soltam o caminho com aspas quando ha espacos, as vezes como
    `file:///...`, e alguns no Linux escapam os espacos com barra invertida.
    """
    bruto = texto.strip()
    if not bruto or "\n" in bruto:
        return []
    if bruto.startswith("file://"):
        from urllib.parse import unquote, urlparse

        bruto = unquote(urlparse(bruto).path)
        if bruto.startswith("/") and len(bruto) > 3 and bruto[2] == ":":
            bruto = bruto[1:]  # /C:/foto.png -> C:/foto.png
    entre_aspas = False
    for par in ('"', "'"):
        if len(bruto) > 1 and bruto.startswith(par) and bruto.endswith(par):
            bruto = bruto[1:-1]
            entre_aspas = True
            break
    bruto = bruto.strip()
    if not bruto:
        return []
    opcoes = [bruto]
    if not entre_aspas:
        desfeito = sistema.desescapar_caminho(bruto)
        if desfeito != bruto:
            opcoes.append(desfeito)
    return [Path(opcao).expanduser() for opcao in opcoes]


def parece_imagem(texto: str, *, so_absoluto: bool = False) -> Path | None:
    """Reconhece um caminho de imagem solto na linha (ex.: arrastado para o terminal).

    `so_absoluto`: para a linha de mensagem -- arrastar sempre solta o caminho
    completo, e assim digitar "main.py" numa conversa nao envia o arquivo.
    """
    for caminho in _candidatos(texto):
        if so_absoluto and not caminho.is_absolute():
            continue
        try:
            if caminho.suffix.lower() in EXTENSOES and caminho.is_file():
                return caminho
        except OSError:
            continue
    return None


def parece_arquivo(texto: str, *, so_absoluto: bool = False) -> Path | None:
    """Como `parece_imagem`, mas aceita qualquer arquivo existente."""
    imagem = parece_imagem(texto, so_absoluto=so_absoluto)
    if imagem:
        return imagem
    if len(texto.strip()) < 4:
        return None
    for caminho in _candidatos(texto):
        if so_absoluto and not caminho.is_absolute():
            continue
        try:
            if caminho.is_file():
                return caminho
        except OSError:
            continue
    return None


def da_area_de_transferencia(pasta: str | Path) -> Path | None:
    """Pega a imagem copiada (ctrl+c) e salva num arquivo; devolve o caminho.

    Funciona com imagem copiada de um editor/navegador (vem como bitmap) e
    tambem com arquivo copiado no explorador (vem como lista de caminhos).
    """
    try:
        from PIL import ImageGrab
    except ImportError as exc:  # pragma: no cover
        raise ImagemError(t("install Pillow to paste images")) from exc

    try:
        conteudo = ImageGrab.grabclipboard()
    except Exception as exc:
        raise ImagemError(
            sistema.dica_area_de_transferencia(
                t("could not read the clipboard: {error}", error=exc)
            )
        ) from exc

    if conteudo is None:
        raise ImagemError(t("there is no image in the clipboard"))

    if isinstance(conteudo, list):  # arquivos copiados no explorador
        for item in conteudo:
            caminho = Path(str(item)).expanduser()
            if caminho.is_file() and caminho.suffix.lower() in EXTENSOES:
                return caminho
        raise ImagemError(t("the copied files are not images"))

    destino = Path(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"pasted_{int(time.time() * 1000)}.png"
    try:
        conteudo.save(arquivo, format="PNG")
    except Exception as exc:
        raise ImagemError(t("failed to save the pasted image: {error}", error=exc)) from exc
    return arquivo
