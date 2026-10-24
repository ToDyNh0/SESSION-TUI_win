"""Frase de recuperacao do Session (mnemonico estilo Monero, 13 palavras).

Porta direta de `ts/session/crypto/mnemonic.ts` do session-desktop: lista de
1626 palavras em ingles, prefixo de 3 letras e palavra de checksum via CRC-32.
O seed real da conta tem 16 bytes (= 12 palavras + 1 de checksum).
"""

from __future__ import annotations

import json
import zlib
from pathlib import Path

from .i18n import t

PREFIX_LEN = 3
_WORDLIST_PATH = Path(__file__).with_name("wordlist_english.json")
_words: list[str] | None = None
_trunc: list[str] | None = None


class MnemonicError(ValueError):
    """Frase invalida: palavra desconhecida, tamanho errado ou checksum."""


def _load() -> tuple[list[str], list[str]]:
    global _words, _trunc
    if _words is None:
        try:
            words = json.loads(_WORDLIST_PATH.read_text(encoding="utf-8"))
        except OSError as exc:
            raise MnemonicError(t("wordlist not found at {path}", path=_WORDLIST_PATH)) from exc
        if not isinstance(words, list) or len(words) != 1626:
            raise MnemonicError(t("invalid wordlist: 1626 words expected"))
        _words = words
        _trunc = [w[:PREFIX_LEN] for w in words]
    return _words, _trunc  # type: ignore[return-value]


def _swap_endian_4byte(hex4: str) -> str:
    if len(hex4) != 8:
        raise MnemonicError(t("invalid length: {n}", n=len(hex4)))
    return hex4[6:8] + hex4[4:6] + hex4[2:4] + hex4[0:2]


def _checksum_index(words: list[str]) -> int:
    trimmed = "".join(w[:PREFIX_LEN] for w in words)
    return (zlib.crc32(trimmed.encode("utf-8")) & 0xFFFFFFFF) % len(words)


def encode(seed: bytes) -> str:
    """seed (16 bytes) -> frase de 13 palavras."""
    words, _ = _load()
    n = len(words)
    seed_hex = seed.hex()
    if len(seed_hex) % 8 != 0:
        raise MnemonicError(t("the seed must be a multiple of 4 bytes"))

    out: list[str] = []
    for i in range(0, len(seed_hex), 8):
        x = int(_swap_endian_4byte(seed_hex[i : i + 8]), 16)
        w1 = x % n
        w2 = (x // n + w1) % n
        w3 = (x // n // n + w2) % n
        out += [words[w1], words[w2], words[w3]]

    out.append(out[_checksum_index(out)])  # palavra de checksum
    return " ".join(out)


def decode(phrase: str) -> bytes:
    """Frase de 13 palavras -> seed em bytes."""
    words, trunc = _load()
    n = len(words)
    wlist = phrase.lower().split()

    if len(wlist) < 12:
        raise MnemonicError(t("too few words (13 expected)"))
    if len(wlist) > 13:
        raise MnemonicError(t("too many words (13 expected)"))
    if len(wlist) % 3 == 2:
        raise MnemonicError(t("invalid number of words"))
    if len(wlist) % 3 == 0:
        raise MnemonicError(t("the last word (checksum) is missing"))

    checksum_word = wlist.pop()

    out = ""
    for i in range(0, len(wlist), 3):
        try:
            w1 = trunc.index(wlist[i][:PREFIX_LEN])
            w2 = trunc.index(wlist[i + 1][:PREFIX_LEN])
            w3 = trunc.index(wlist[i + 2][:PREFIX_LEN])
        except ValueError as exc:
            raise MnemonicError(t("unknown word near {word}", word=repr(wlist[i]))) from exc
        x = w1 + n * ((n - w1 + w2) % n) + n * n * ((n - w2 + w3) % n)
        if x % n != w1:
            raise MnemonicError(t("failed to decode the phrase"))
        out += _swap_endian_4byte(f"{x:08x}")

    expected = wlist[_checksum_index(wlist)]
    if expected[:PREFIX_LEN] != checksum_word[:PREFIX_LEN]:
        raise MnemonicError(t("invalid checksum: check the last word"))

    return bytes.fromhex(out)
