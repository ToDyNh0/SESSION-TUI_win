"""Identidade Session: seed -> Ed25519 -> X25519 -> Session ID.

Derivacao identica a `sessionGenerateKeyPair` do session-desktop
(`ts/util/accountManager.ts`):

    seed (16B) -> completado com zeros ate 32B
               -> crypto_sign_seed_keypair()             (Ed25519)
               -> crypto_sign_ed25519_pk_to_curve25519() (X25519)
    Session ID = "05" + hex(pubkey X25519)
"""

from __future__ import annotations

from dataclasses import dataclass

from nacl import bindings as sodium
from nacl.utils import random as random_bytes

from . import mnemonic
from .i18n import t

SEED_SIZE = 16
ED25519_SEED_SIZE = 32
SESSION_ID_PREFIX = "05"


class InvalidSessionID(ValueError):
    """Session ID fora do formato `05` + 64 hexadecimais."""


def parse_session_id(session_id: str) -> bytes:
    """Valida um Session ID e devolve a pubkey X25519 (32 bytes)."""
    sid = session_id.strip().lower()
    if len(sid) != 66:
        raise InvalidSessionID(t("a Session ID has 66 characters (this one has {n})", n=len(sid)))
    if not sid.startswith(SESSION_ID_PREFIX):
        prefix = sid[:2]
        if prefix in ("03", "15", "25"):
            raise InvalidSessionID(
                t(
                    "prefix {prefix} is not a 1-to-1 account "
                    "(groups/blinded community IDs are not supported here)",
                    prefix=repr(prefix),
                )
            )
        raise InvalidSessionID(
            t("a Session ID starts with 05 (this one starts with {prefix})", prefix=repr(prefix))
        )
    try:
        return bytes.fromhex(sid[2:])
    except ValueError as exc:
        raise InvalidSessionID(t("the Session ID is not hexadecimal")) from exc


@dataclass(frozen=True)
class Identity:
    """Par de chaves de uma conta Session."""

    seed: bytes  # 16 bytes: a entropia da frase de recuperacao
    ed25519_pk: bytes  # 32 bytes
    ed25519_sk: bytes  # 64 bytes (seed || pubkey, formato libsodium)
    x25519_pk: bytes  # 32 bytes
    x25519_sk: bytes  # 32 bytes

    @property
    def session_id(self) -> str:
        return SESSION_ID_PREFIX + self.x25519_pk.hex()

    @property
    def mnemonic(self) -> str:
        return mnemonic.encode(self.seed)

    @classmethod
    def from_seed(cls, seed: bytes) -> "Identity":
        if len(seed) not in (SEED_SIZE, ED25519_SEED_SIZE):
            raise ValueError(
                t("the seed must have {a} or {b} bytes", a=SEED_SIZE, b=ED25519_SEED_SIZE)
            )
        padded = seed.ljust(ED25519_SEED_SIZE, b"\x00")
        ed_pk, ed_sk = sodium.crypto_sign_seed_keypair(padded)
        return cls(
            seed=seed,
            ed25519_pk=ed_pk,
            ed25519_sk=ed_sk,
            x25519_pk=sodium.crypto_sign_ed25519_pk_to_curve25519(ed_pk),
            x25519_sk=sodium.crypto_sign_ed25519_sk_to_curve25519(ed_sk),
        )

    @classmethod
    def generate(cls) -> "Identity":
        return cls.from_seed(random_bytes(SEED_SIZE))

    @classmethod
    def from_mnemonic(cls, phrase: str) -> "Identity":
        return cls.from_seed(mnemonic.decode(phrase))


def session_id_from_ed25519(ed25519_pk: bytes) -> str:
    """Session ID do remetente a partir da pubkey Ed25519 embutida na mensagem."""
    return SESSION_ID_PREFIX + sodium.crypto_sign_ed25519_pk_to_curve25519(ed25519_pk).hex()


def sign_detached(message: bytes, ed25519_sk: bytes) -> bytes:
    """Assinatura Ed25519 de 64 bytes (PyNaCl so expoe a versao anexada)."""
    return sodium.crypto_sign(message, ed25519_sk)[: sodium.crypto_sign_BYTES]


def verify_detached(message: bytes, signature: bytes, ed25519_pk: bytes) -> bool:
    if len(signature) != sodium.crypto_sign_BYTES:
        return False
    try:
        sodium.crypto_sign_open(signature + message, ed25519_pk)
    except Exception:
        return False
    return True
