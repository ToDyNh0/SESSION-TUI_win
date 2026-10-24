"""Anexos do Session: criptografia, file server e deteccao de imagem.

Formato usado aqui e o classico (compativel com todas as versoes do Session,
desktop/iOS/Android), confirmado em `ts/util/crypto/attachmentsEncrypter.ts`:

    dados -> padding de anexo (1.05^n, minimo 541 B)
          -> AES-256-CBC (PKCS7) com key[0:32] e IV aleatorio
          -> blob = IV ‖ ciphertext ‖ HMAC-SHA256(key[32:64], IV ‖ ciphertext)
          -> digest = SHA-256(blob)
          -> upload no file server (POST /file) -> id -> url

A `AttachmentPointer` leva url, key (64 B), digest e `size` (tamanho original,
sem padding). O destinatario confere HMAC e digest, decifra e corta no `size`.

O formato novo da libsession (crypto_secretstream, marcado com `#d` na url) nao
e gerado aqui de proposito: o classico e aceito por todos os clientes.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
from cryptography.hazmat.primitives import padding as crypto_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from nacl.utils import random as random_bytes

from . import onion
from .i18n import t

FILE_SERVER_HOST = "filev2.getsession.org"
FILE_SERVER_URL = f"https://{FILE_SERVER_HOST}"
# O file server publica a chave Ed25519; a cebola cifra para a X25519
# correspondente (= crypto_sign_ed25519_pk_to_curve25519 da Ed25519).
FILE_SERVER_ED25519 = "b8eef9821445ae16e2e97ef8aa6fe782fd11ad5253cd6723b281341dba22e371"
FILE_SERVER_X25519 = "09324794aa9c11948189762d198c618148e9136ac9582068180661208927ef34"

KEY_SIZE = 64  # 32 para AES + 32 para HMAC
IV_SIZE = 16
MAC_SIZE = 32
PADDING_MIN = 541
MAX_ATTACHMENT_SIZE = 10_000_000  # mesmo limite do cliente oficial

# Formato novo (libsession `session::attachments`), usado pelos clientes atuais:
#   'S' | header(24) | chunks de ate 32 KiB cifrados com crypto_secretstream
# O texto em claro comeca com padding: zeros, um 0x01, e so entao os dados.
STREAM_MAGIC = 0x53  # 'S'
STREAM_HEADER = 24
STREAM_CHUNK = 32_768
STREAM_OVERHEAD = 17
STREAM_KEY_SIZE = 32

IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".ico": "image/x-icon",
    ".avif": "image/avif",
}


class AttachmentError(RuntimeError):
    """Falha ao cifrar, enviar, baixar ou decifrar um anexo."""


# --- padding ----------------------------------------------------------------


def pad_attachment(data: bytes) -> bytes:
    """Padding que esconde o tamanho real (igual a `addAttachmentPadding`)."""
    if not data:
        padded_size = PADDING_MIN
    else:
        crescimento = math.floor(1.05 ** math.ceil(math.log(len(data)) / math.log(1.05)))
        padded_size = max(PADDING_MIN, crescimento)
    if padded_size > MAX_ATTACHMENT_SIZE and len(data) <= MAX_ATTACHMENT_SIZE:
        padded_size = MAX_ATTACHMENT_SIZE
    if padded_size < len(data):
        padded_size = len(data)
    return data + b"\x00" * (padded_size - len(data))


def unpad_attachment(data: bytes, expected_size: int | None) -> bytes:
    """Corta o padding usando o `size` declarado na AttachmentPointer."""
    if not expected_size or expected_size <= 0 or len(data) <= expected_size:
        return data
    return data[:expected_size]


# --- criptografia -----------------------------------------------------------


@dataclass
class EncryptedAttachment:
    blob: bytes  # o que vai para o file server
    key: bytes  # 64 bytes (vai na AttachmentPointer)
    digest: bytes  # SHA-256 do blob
    plain_size: int  # tamanho original, sem padding


def encrypt_attachment(plaintext: bytes) -> EncryptedAttachment:
    if len(plaintext) > MAX_ATTACHMENT_SIZE:
        raise AttachmentError(
            t("file too large: {n} B (limit {max})", n=len(plaintext), max=MAX_ATTACHMENT_SIZE)
        )
    key = random_bytes(KEY_SIZE)
    iv = random_bytes(IV_SIZE)

    padder = crypto_padding.PKCS7(algorithms.AES.block_size).padder()
    bloco = padder.update(pad_attachment(plaintext)) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key[:32]), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(bloco) + encryptor.finalize()

    mac = hmac.new(key[32:], iv + ciphertext, hashlib.sha256).digest()
    blob = iv + ciphertext + mac
    return EncryptedAttachment(
        blob=blob,
        key=key,
        digest=hashlib.sha256(blob).digest(),
        plain_size=len(plaintext),
    )


def decrypt_attachment(
    blob: bytes, key: bytes, *, digest: bytes | None = None, size: int | None = None
) -> bytes:
    if len(key) != KEY_SIZE:
        raise AttachmentError(
            t("the attachment key must have {n} bytes (it has {m})", n=KEY_SIZE, m=len(key))
        )
    if len(blob) < IV_SIZE + MAC_SIZE:
        raise AttachmentError(t("attachment too short"))

    iv = blob[:IV_SIZE]
    ciphertext = blob[IV_SIZE : -MAC_SIZE]
    mac = blob[-MAC_SIZE:]

    esperado = hmac.new(key[32:], iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, esperado):
        raise AttachmentError(t("attachment HMAC does not match"))
    if digest and not hmac.compare_digest(hashlib.sha256(blob).digest(), digest):
        raise AttachmentError(t("attachment digest does not match"))

    decryptor = Cipher(algorithms.AES(key[:32]), modes.CBC(iv)).decryptor()
    bloco = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = crypto_padding.PKCS7(algorithms.AES.block_size).unpadder()
    try:
        dados = unpadder.update(bloco) + unpadder.finalize()
    except ValueError as exc:
        raise AttachmentError(t("invalid AES padding: {error}", error=exc)) from exc
    return unpad_attachment(dados, size)


def decrypt_stream_attachment(blob: bytes, key: bytes) -> bytes:
    """Decifra o formato novo (crypto_secretstream, chave de 32 bytes).

    E o que os clientes Session atuais enviam. A url do anexo costuma vir com
    o fragmento `#d`, mas aqui o que decide e o tamanho da chave.
    """
    from nacl import bindings as sodium

    if len(key) != STREAM_KEY_SIZE:
        raise AttachmentError(
            t("the stream key must have {n} bytes (it has {m})", n=STREAM_KEY_SIZE, m=len(key))
        )
    if len(blob) < 1 + STREAM_HEADER + STREAM_OVERHEAD:
        raise AttachmentError(t("attachment too short for the new format"))
    if blob[0] != STREAM_MAGIC:
        raise AttachmentError(t("unknown encryption type: {kind}", kind=f"0x{blob[0]:02x}"))

    estado = sodium.crypto_secretstream_xchacha20poly1305_state()
    sodium.crypto_secretstream_xchacha20poly1305_init_pull(
        estado, blob[1 : 1 + STREAM_HEADER], key
    )

    posicao = 1 + STREAM_HEADER
    partes: list[bytes] = []
    final = False
    while posicao < len(blob):
        tamanho = min(len(blob) - posicao, STREAM_CHUNK + STREAM_OVERHEAD)
        try:
            pedaco, tag = sodium.crypto_secretstream_xchacha20poly1305_pull(
                estado, blob[posicao : posicao + tamanho]
            )
        except Exception as exc:
            raise AttachmentError(t("invalid key or corrupted data: {error}", error=exc)) from exc
        partes.append(pedaco)
        posicao += tamanho
        if tag == sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL:
            final = True
            break
    if not final:
        raise AttachmentError(t("the stream ended without the final tag"))

    dados = b"".join(partes)
    inicio = 0
    while inicio < len(dados) and dados[inicio] == 0x00:
        inicio += 1
    if inicio >= len(dados) or dados[inicio] != 0x01:
        raise AttachmentError(t("invalid attachment padding"))
    return dados[inicio + 1 :]


def decrypt_any(
    blob: bytes, key: bytes, *, digest: bytes | None = None, size: int | None = None
) -> bytes:
    """Decifra um anexo escolhendo o formato pelo tamanho da chave.

    64 bytes -> formato classico (AES-CBC + HMAC + digest).
    32 bytes -> formato novo (crypto_secretstream), sem digest nem `size`.
    """
    if len(key) == STREAM_KEY_SIZE:
        return decrypt_stream_attachment(blob, key)
    return decrypt_attachment(blob, key, digest=digest, size=size)


# --- file server ------------------------------------------------------------


@dataclass
class UploadResult:
    file_id: str
    url: str
    expires_ms: int | None = None


class FileServer:
    """Upload e download no file server do Session (direto ou via onion)."""

    def __init__(
        self,
        *,
        network=None,  # SnodeNetwork, para montar caminhos onion
        timeout: float = 60.0,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.network = network
        self.timeout = timeout
        self._log = log or (lambda _msg: None)
        self._http = requests.Session()

    @property
    def use_onion(self) -> bool:
        return bool(self.network and self.network.use_onion)

    # -- onion --------------------------------------------------------------

    def _onion(self, *, endpoint: str, method: str, body: bytes | None) -> tuple[int, bytes]:
        path = self.network.build_path(_FakeDestination())
        built = onion.build_server_onion_request(
            path,
            host=FILE_SERVER_HOST,
            x25519_pubkey=FILE_SERVER_X25519,
            endpoint=endpoint,
            method=method,
            body=body,
        )
        response = self._http.post(
            path[0].onion_url,
            data=built.payload,
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.timeout,
            verify=False,
        )
        if response.status_code != 200:
            raise AttachmentError(
                t("onion via {node}: HTTP {code}", node=path[0].short, code=response.status_code)
            )
        return built.parse_raw_response(response.content)

    # -- upload / download ---------------------------------------------------

    def upload(self, blob: bytes) -> UploadResult:
        if self.use_onion:
            try:
                code, body = self._onion(endpoint="/file", method="POST", body=blob)
                if 200 <= code < 300:
                    return self._parse_upload(body)
                self._log(t("file server answered {code} via onion; trying direct", code=code))
            except (AttachmentError, onion.OnionError, requests.RequestException) as exc:
                self._log(t("upload via onion failed ({error}); trying direct", error=exc))

        try:
            response = self._http.post(
                f"{FILE_SERVER_URL}/file",
                data=blob,
                headers={"Content-Type": "application/octet-stream"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AttachmentError(t("upload failed: {error}", error=exc)) from exc
        return self._parse_upload(response.content)

    def _parse_upload(self, body: bytes) -> UploadResult:
        import json

        try:
            data = json.loads(body)
            file_id = str(data["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AttachmentError(
                t("unexpected file server response: {body}", body=repr(body[:120]))
            ) from exc
        expires = data.get("expires")
        return UploadResult(
            file_id=file_id,
            url=f"{FILE_SERVER_URL}/file/{file_id}",
            expires_ms=int(float(expires) * 1000) if expires else None,
        )

    def download(self, url: str) -> bytes:
        file_id = url.split("#")[0].rstrip("/").rsplit("/", 1)[-1]
        if not file_id:
            raise AttachmentError(t("invalid attachment url: {url}", url=url))

        if self.use_onion:
            try:
                code, body = self._onion(endpoint=f"/file/{file_id}", method="GET", body=None)
                if 200 <= code < 300 and body:
                    return body
                self._log(t("download via onion returned {code}; trying direct", code=code))
            except (AttachmentError, onion.OnionError, requests.RequestException) as exc:
                self._log(t("download via onion failed ({error}); trying direct", error=exc))

        alvo = url.split("#")[0]
        if FILE_SERVER_HOST not in alvo:
            alvo = f"{FILE_SERVER_URL}/file/{file_id}"
        try:
            response = self._http.get(alvo, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise AttachmentError(t("download failed: {error}", error=exc)) from exc
        return response.content


class _FakeDestination:
    """Placeholder: caminhos onion para servidor nao excluem nenhum snode."""

    ed25519 = ""
    x25519 = ""


# --- utilidades de arquivo --------------------------------------------------


def guess_content_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return IMAGE_EXTENSIONS[ext]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def is_image(content_type: str | None, name: str | None = None) -> bool:
    if content_type and content_type.lower().startswith("image/"):
        return True
    if name:
        return Path(name).suffix.lower() in IMAGE_EXTENSIONS
    return False


def image_dimensions(data: bytes) -> tuple[int | None, int | None]:
    """Largura e altura, se o Pillow estiver disponivel e o formato for imagem."""
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as img:
            return img.width, img.height
    except Exception:
        return None, None
