"""Textos da interface: ingles (padrao) ou portugues.

O texto em ingles e a propria chave: `t("sent to {n} nodes", n=3)`. Em
portugues a chave e procurada em `traducao_pt.PT`; sem traducao, sai o ingles
mesmo -- um texto faltando nunca derruba o programa. O `selftest` confere que
todo `t("...")` do codigo tem traducao e os mesmos campos `{...}`.

Textos longos (ajuda, explicacoes) ficam em `longo(nome)`.
"""

from __future__ import annotations

IDIOMAS = ("en", "pt")
PADRAO = "en"
NOMES = {"en": "English", "pt": "Português"}

_APELIDOS = {
    "en": "en",
    "english": "en",
    "ingles": "en",
    "inglês": "en",
    "en-us": "en",
    "en-gb": "en",
    "pt": "pt",
    "pt-br": "pt",
    "br": "pt",
    "portugues": "pt",
    "português": "pt",
    "portuguese": "pt",
}

_idioma = PADRAO


def normalizar(valor: str | None) -> str | None:
    """'pt-BR', 'portugues', 'english'... -> 'pt' / 'en' (ou None)."""
    return _APELIDOS.get((valor or "").strip().lower().replace("_", "-"))


def definir_idioma(valor: str | None) -> str:
    global _idioma
    _idioma = normalizar(valor) or PADRAO
    return _idioma


def idioma() -> str:
    return _idioma


def t(texto: str, /, **campos) -> str:
    if _idioma == "pt":
        from .traducao_pt import PT

        texto = PT.get(texto, texto)
    return texto.format(**campos) if campos else texto


def longo(nome: str) -> str:
    if _idioma == "pt":
        from .traducao_pt import LONGOS_PT

        if nome in LONGOS_PT:
            return LONGOS_PT[nome]
    return LONGOS_EN[nome]


LONGOS_EN = {
    "help": """IMAGES AND FILES   (any type, up to 10 MB)

  /img <path> [caption]      sends an image or file
                             aliases: /file, /attach
  drag into the window       drops the path in the input; enter sends
  ctrl+v  (or ctrl+g, /paste)  sends the image in the clipboard
  /download [n]  or ctrl+b   downloads the received attachment and draws it
  /auto on|off               download without asking (default: off, asks)
  /open [path]               opens the download in the system's default app
  /view <path>               draws an image in the panel
  /mode                      explains the drawing modes
  /mode half|blocks          changes the mode (sixel/tgp: start with --mode sixel)
  /width <cells>             drawing size (default 44)

CONVERSATIONS

  /to <session_id>           opens (or creates) the conversation
  /add <session_id>          only adds it to the list, without switching
  /profile [id]  or f2       contact card: full ID, nickname, copy
                             (right click on the list does the same)
  /nick <nickname>           nickname for the open conversation
  /rm [id]                   removes the conversation from the list
  /typing                    sends the "typing..." notice

MY ACCOUNT

  /me  or f3  or the avatar in the top left corner
                             name, Session ID, phrase, password, kill switch
  /name <name>               display name (sent along with your messages)
  /phrase                    shows the recovery phrase (careful!)
  /protect                   encrypts the seed on disk with a password
                             (Argon2id + XChaCha20-Poly1305)
  /unprotect                 removes the password (back to clear text)
  /killswitch                erase everything after a time without access
  /lang en|pt                interface language (English / Português)
  /removeall                 ERASES everything and starts a new account;
                             asks twice and can notify your contacts

NETWORK AND SCREEN

  /poll  or ctrl+r           fetches messages now
  /network                   known nodes, swarm and network clock
  /onion on|off              3-hop onion routing (hides your IP)
  /log [n|clear]             shows/hides the network log (default: hidden)
  /clear  or ctrl+l          clears the conversation panel
  /help  or f1               this window
  /quit  or ctrl+c           closes

Any other line becomes a message to the open conversation.""",
    "image_modes": """how images are drawn:

  half    (default) two pixels per cell: the top half becomes the text color
          and the bottom half the background color, on the half-block
          character. The most detail using only ANSI colors -- works in any
          terminal, cmd.exe included, and never writes outside Textual.

  blocks  one pixel per cell, using the full colored block. Half the vertical
          resolution of 'half', but only uses the text color: for terminals
          that paint the background badly or leave lines between cells.

  sixel   a real image, in pixels, via the Sixel protocol. Needs Windows
          Terminal 1.22+, WezTerm, foot, mlterm or xterm built with sixel.
  tgp     a real image through the Kitty graphics protocol (Kitty, Ghostty).
  auto    probes the terminal and picks tgp, sixel or half by itself.

The last three must probe the terminal (write a question on the screen and
read the answer from the keyboard), which is only safe BEFORE the interface
opens -- so they are chosen on the command line:  session-tui tui --mode sixel""",
    # paragrafos sem quebra manual: o Textual quebra na largura da janela
    "killswitch": (
        "If nobody uses this account for the time below, everything is erased: "
        "key, recovery phrase, history, attachments and contacts.\n\n"
        "Checked whenever the app opens and, with the automatic check on, "
        "every hour even with the app closed. Opening the app counts as access."
    ),
}
