"""Protecao da conta com senha: Argon2id + XChaCha20-Poly1305.

A frase de recuperacao (e o seed de onde ela sai) *e* a conta: quem le o
arquivo vira voce. Com senha, o que fica no disco e so um bloco cifrado:

    senha --Argon2id(sal, ops, mem)--> chave de 32 B
    conteudo --XChaCha20-Poly1305(chave, nonce)--> bloco cifrado

O sal, o nonce e os parametros do Argon2id ficam em claro no arquivo (e assim
que deve ser -- eles nao sao segredo, e sao necessarios para abrir). O Session
ID tambem fica em claro: ele e o seu endereco publico, e permite a interface
dizer de qual conta se trata antes de pedir a senha.

Nada disso ajuda se a senha for fraca: o Argon2id so encarece a tentativa.
"""

from __future__ import annotations

import json
from base64 import b64decode, b64encode

from nacl import bindings as sodium
from nacl import pwhash
from nacl.utils import random as random_bytes

from .i18n import t

ALGORITMO = "argon2id-xchacha20poly1305"
VERSAO = 1
CHAVE_BYTES = 32
NONCE_BYTES = sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES  # 24
SAL_BYTES = pwhash.argon2id.SALTBYTES  # 16

# ~0,3 s e ~256 MB por tentativa: desconfortavel para quem tenta adivinhar,
# imperceptivel para quem sabe a senha.
OPS_PADRAO = pwhash.argon2id.OPSLIMIT_MODERATE
MEM_PADRAO = pwhash.argon2id.MEMLIMIT_MODERATE


class CofreError(RuntimeError):
    """Problema ao proteger ou abrir a conta."""


class SenhaNecessaria(CofreError):
    """A conta esta protegida e nenhuma senha foi dada."""


class SenhaErrada(CofreError):
    """A senha nao abre este arquivo."""


def esta_protegido(bruto: dict) -> bool:
    return isinstance(bruto, dict) and bruto.get("protegido") == ALGORITMO


def _derivar(senha: str, sal: bytes, ops: int, mem: int) -> bytes:
    if not senha:
        raise CofreError(t("empty password"))
    try:
        return pwhash.argon2id.kdf(
            CHAVE_BYTES, senha.encode("utf-8"), sal, opslimit=ops, memlimit=mem
        )
    except Exception as exc:  # memoria insuficiente, por exemplo
        raise CofreError(t("could not derive the key: {error}", error=exc)) from exc


def proteger(conteudo: dict, senha: str, *, publico: dict | None = None) -> dict:
    """Cifra `conteudo` com a senha e devolve o envelope para salvar."""
    sal = random_bytes(SAL_BYTES)
    nonce = random_bytes(NONCE_BYTES)
    chave = _derivar(senha, sal, OPS_PADRAO, MEM_PADRAO)
    claro = json.dumps(conteudo, ensure_ascii=False).encode("utf-8")
    cifrado = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(claro, None, nonce, chave)

    envelope = {
        "versao": VERSAO,
        "protegido": ALGORITMO,
        "sal": b64encode(sal).decode("ascii"),
        "nonce": b64encode(nonce).decode("ascii"),
        "ops": OPS_PADRAO,
        "mem": MEM_PADRAO,
        "dados": b64encode(cifrado).decode("ascii"),
        "aviso": "password-protected account; without the password this file cannot be opened",
    }
    envelope.update(publico or {})
    return envelope


def abrir(envelope: dict, senha: str | None) -> dict:
    """Decifra o envelope e devolve o conteudo original."""
    if not esta_protegido(envelope):
        raise CofreError(t("this file is not protected"))
    if not senha:
        raise SenhaNecessaria(t("the account is password-protected"))
    try:
        sal = b64decode(envelope["sal"])
        nonce = b64decode(envelope["nonce"])
        cifrado = b64decode(envelope["dados"])
        ops = int(envelope.get("ops", OPS_PADRAO))
        mem = int(envelope.get("mem", MEM_PADRAO))
    except (KeyError, ValueError, TypeError) as exc:
        raise CofreError(t("the protected account file is corrupted")) from exc

    chave = _derivar(senha, sal, ops, mem)
    try:
        claro = sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(cifrado, None, nonce, chave)
    except Exception as exc:
        raise SenhaErrada(t("wrong password")) from exc
    try:
        return json.loads(claro)
    except ValueError as exc:
        raise CofreError(t("the decrypted content is invalid")) from exc
