"""Onion requests (requisicoes em cebola) para service nodes do Session.

Porta de `src/onionreq/builder.cpp` + `src/onionreq/hop_encryption.cpp` da
libsession-util. Cada camada e cifrada com XChaCha20-Poly1305 usando uma chave
efemera diferente, de modo que cada no sabe apenas de quem recebeu e para quem
entregar:

    cliente -> hop1 -> hop2 -> hop3 -> snode de destino

Formato de cada camada:   [tamanho:4 LE][blob cifrado][json de roteamento]
Chave de cada salto:      blake2b-32( X25519(a, B) || A || B )
"""

from __future__ import annotations

import hashlib
import json
from base64 import b64decode
from dataclasses import dataclass

from nacl import bindings as sodium

from .i18n import t

NONCE_BYTES = sodium.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES  # 24
ENC_TYPE = "xchacha20"
ONION_PATH_SIZE = 3


class OnionError(RuntimeError):
    """Falha ao montar, enviar ou decifrar uma requisicao em cebola."""


def _shared_key(eph_pk: bytes, eph_sk: bytes, remote_pk: bytes) -> bytes:
    """blake2b-32( X25519(sk_efemera, pk_remota) || pk_efemera || pk_remota )."""
    secret = sodium.crypto_scalarmult(eph_sk, remote_pk)
    h = hashlib.blake2b(digest_size=32)
    h.update(secret)
    h.update(eph_pk)
    h.update(remote_pk)
    return h.digest()


def _encrypt_layer(plaintext: bytes, remote_pk: bytes) -> tuple[bytes, bytes, bytes]:
    """Cifra uma camada; devolve (nonce||ciphertext, pubkey_efemera, sk_efemera)."""
    eph_pk, eph_sk = sodium.crypto_box_keypair()
    key = _shared_key(eph_pk, eph_sk, remote_pk)
    nonce = sodium.randombytes(NONCE_BYTES)
    ciphertext = sodium.crypto_aead_xchacha20poly1305_ietf_encrypt(
        plaintext, None, nonce, key
    )
    return nonce + ciphertext, eph_pk, eph_sk


def _decrypt_layer(payload: bytes, eph_pk: bytes, eph_sk: bytes, remote_pk: bytes) -> bytes:
    if len(payload) <= NONCE_BYTES:
        raise OnionError(t("response too short to contain nonce + tag"))
    key = _shared_key(eph_pk, eph_sk, remote_pk)
    nonce, ciphertext = payload[:NONCE_BYTES], payload[NONCE_BYTES:]
    try:
        return sodium.crypto_aead_xchacha20poly1305_ietf_decrypt(
            ciphertext, None, nonce, key
        )
    except Exception as exc:  # CryptoError
        raise OnionError(t("failed to decrypt the response: {error}", error=exc)) from exc


def _size_prefix(length: int) -> bytes:
    return length.to_bytes(4, "little")


def _json_bytes(obj: dict) -> bytes:
    # separators compactos: o formato nao exige, mas evita bytes inuteis
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def _bt_list(items: list[bytes]) -> bytes:
    """bencode de uma lista de strings: l<tam>:<dados>...e."""
    out = bytearray(b"l")
    for item in items:
        out += str(len(item)).encode("ascii") + b":" + item
    out += b"e"
    return bytes(out)


def _bt_parse_list(data: bytes) -> list[bytes]:
    if not data.startswith(b"l"):
        raise OnionError(t("v4 response is not a bencode list"))
    items: list[bytes] = []
    pos = 1
    while pos < len(data) and data[pos : pos + 1] != b"e":
        colon = data.find(b":", pos)
        if colon < 0:
            raise OnionError(t("malformed v4 response"))
        try:
            length = int(data[pos:colon])
        except ValueError as exc:
            raise OnionError(t("invalid length in v4 response")) from exc
        start = colon + 1
        items.append(data[start : start + length])
        pos = start + length
    return items


@dataclass
class BuiltOnion:
    """Payload pronto para o primeiro salto + chaves para abrir a resposta."""

    payload: bytes
    final_eph_pk: bytes
    final_eph_sk: bytes
    destination_x25519: bytes
    v4: bool = False  # destino tipo servidor (file server): resposta bencode

    def parse_raw_response(self, body: bytes) -> tuple[int, bytes]:
        """Resposta v4 (servidor): devolve (codigo HTTP, corpo em bytes)."""
        plaintext = _decrypt_layer(
            body, self.final_eph_pk, self.final_eph_sk, self.destination_x25519
        )
        items = _bt_parse_list(plaintext)
        if not items:
            raise OnionError(t("empty v4 response"))
        try:
            info = json.loads(items[0])
        except ValueError as exc:
            raise OnionError(t("v4 header is not JSON")) from exc
        code = int(info.get("code", 0))
        return code, items[1] if len(items) > 1 else b""

    def parse_response(self, body: bytes) -> dict:
        """Decifra a resposta do destino e devolve o JSON do corpo."""
        if self.v4:
            code, payload = self.parse_raw_response(body)
            if not 200 <= code < 300:
                raise OnionError(t("destination answered HTTP {code}: {body}", code=code, body=repr(payload[:200])))
            try:
                return json.loads(payload) if payload else {}
            except ValueError:
                return {"body": payload}

        raw = body
        try:  # resposta v3: {"result": base64(nonce||ciphertext)}
            wrapper = json.loads(body)
            if isinstance(wrapper, dict) and isinstance(wrapper.get("result"), str):
                raw = b64decode(wrapper["result"])
        except (ValueError, UnicodeDecodeError):
            pass
        if raw is body:
            try:
                raw = b64decode(body, validate=True)
            except Exception:
                raw = body

        plaintext = _decrypt_layer(
            raw, self.final_eph_pk, self.final_eph_sk, self.destination_x25519
        )
        try:
            outer = json.loads(plaintext)
        except ValueError as exc:
            raise OnionError(t("decrypted response is not JSON")) from exc

        status = outer.get("status_code", outer.get("status"))
        if status is not None and not 200 <= int(status) < 300:
            raise OnionError(
                t("destination answered HTTP {code}: {body}", code=status, body=repr(outer.get("body")))
            )

        body_field = outer.get("body")
        if isinstance(body_field, str):
            try:
                return json.loads(body_field)
            except ValueError:
                return {"body": body_field}
        if isinstance(body_field, dict):
            return body_field
        return outer


def _wrap_hops(path: list, blob: bytes, routing: dict) -> bytes:
    """Envolve o blob em uma camada por salto, de tras para frente.

    Cada camada carrega o roteamento que manda o salto atual entregar ao
    seguinte, junto da chave efemera que o seguinte deve usar.
    """
    eph_pk = b""
    for hop in reversed(path):
        data = _size_prefix(len(blob)) + blob + _json_bytes(routing)
        blob, eph_pk, _ = _encrypt_layer(data, bytes.fromhex(hop.x25519))
        routing = {
            "destination": hop.ed25519,
            "ephemeral_key": eph_pk.hex(),
            "enc_type": ENC_TYPE,
        }
    # O primeiro salto so precisa saber como decifrar a camada externa.
    wrapper = _json_bytes({"ephemeral_key": eph_pk.hex(), "enc_type": ENC_TYPE})
    return _size_prefix(len(blob)) + blob + wrapper


def build_onion_request(
    path: list,  # list[Snode]: os 3 saltos, na ordem
    destination,  # Snode: o snode que executa o RPC
    method: str,
    params: dict,
) -> BuiltOnion:
    """Cebola para um service node (RPC de armazenamento)."""
    if not path:
        raise OnionError(t("empty path"))

    payload = _json_bytes({"method": method, "params": params})

    # Camada do destino: ele responde ao RPC. {"headers": ""} marca "e para voce".
    control = _json_bytes({"headers": ""})
    inner = _size_prefix(len(payload)) + payload + control
    blob, eph_pk, eph_sk = _encrypt_layer(inner, bytes.fromhex(destination.x25519))

    routing = {
        "destination": destination.ed25519,
        "ephemeral_key": eph_pk.hex(),
        "enc_type": ENC_TYPE,
    }
    return BuiltOnion(
        payload=_wrap_hops(path, blob, routing),
        final_eph_pk=eph_pk,
        final_eph_sk=eph_sk,
        destination_x25519=bytes.fromhex(destination.x25519),
    )


def build_server_onion_request(
    path: list,  # list[Snode]: os 3 saltos
    *,
    host: str,
    x25519_pubkey: str,
    endpoint: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict | None = None,
    port: int = 443,
    protocol: str = "https",
) -> BuiltOnion:
    """Cebola para um servidor HTTP do Session (file server), formato v4.

    O ultimo salto faz a requisicao HTTP e devolve a resposta cifrada, entao o
    servidor ve o IP do salto -- nao o seu.
    """
    if not path:
        raise OnionError(t("empty path"))

    final_headers = dict(headers or {})
    if body and "Content-Type" not in final_headers:
        final_headers["Content-Type"] = "application/octet-stream"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    info = _json_bytes({"method": method, "endpoint": endpoint, "headers": final_headers})
    payload = _bt_list([info] + ([body] if body else []))

    server_pk = bytes.fromhex(x25519_pubkey)
    blob, eph_pk, eph_sk = _encrypt_layer(payload, server_pk)

    routing = {
        "host": host,
        "target": "/oxen/v4/lsrpc",  # todos os servidores aceitam onion v4
        "method": "POST",
        "protocol": protocol,
        "port": port,
        "ephemeral_key": eph_pk.hex(),
        "enc_type": ENC_TYPE,
    }
    return BuiltOnion(
        payload=_wrap_hops(path, blob, routing),
        final_eph_pk=eph_pk,
        final_eph_sk=eph_sk,
        destination_x25519=server_pk,
        v4=True,
    )
