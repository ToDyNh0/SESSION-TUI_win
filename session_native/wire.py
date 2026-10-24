"""Formato de fio do Session Protocol v2 (mensagens 1-para-1).

Montagem de uma mensagem (igual a `encode_for_destination_internal` da
libsession-util, `src/session_protocol.cpp`):

    Content (protobuf)
      -> padding em multiplos de 160 bytes, com terminador 0x80
      -> plaintext || ed25519_pk_remetente || assinatura   (sign_for_recipient)
      -> crypto_box_seal() para a pubkey X25519 do destinatario
      -> Envelope (protobuf): type=SESSION_MESSAGE, timestamp, content, proSig
      -> WebSocketMessage (protobuf): REQUEST com o Envelope no corpo
      -> base64 -> campo `data` do RPC `store` do snode

A assinatura cobre (mensagem || pubkey_ed25519_remetente || pubkey_x25519_destinatario),
o que autentica o remetente sem revelar sua identidade para a rede: a pubkey
vai dentro da caixa selada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nacl import bindings as sodium
from nacl.utils import random as random_bytes

from . import keys, proto
from .i18n import t

# --- numeros de campo dos protobufs (proto/SessionProtos.proto) ---------------

ENVELOPE_TYPE = 1
ENVELOPE_SOURCE = 2
ENVELOPE_TIMESTAMP = 5
ENVELOPE_SOURCE_DEVICE = 7
ENVELOPE_CONTENT = 8
ENVELOPE_SERVER_TIMESTAMP = 10
ENVELOPE_PRO_SIG = 11

ENVELOPE_TYPE_SESSION_MESSAGE = 6
ENVELOPE_TYPE_CLOSED_GROUP_MESSAGE = 7

WS_TYPE = 1
WS_REQUEST = 2
WS_RESPONSE = 3
WS_TYPE_REQUEST = 1

WS_REQ_VERB = 1
WS_REQ_PATH = 2
WS_REQ_BODY = 3
WS_REQ_ID = 4

CONTENT_DATA_MESSAGE = 1
CONTENT_TYPING_MESSAGE = 6
CONTENT_UNSEND_REQUEST = 9
CONTENT_EXPIRATION_TYPE = 12
CONTENT_EXPIRATION_TIMER = 13
CONTENT_SIG_TIMESTAMP = 15
CONTENT_PRO_MESSAGE = 16

DATA_BODY = 1
DATA_ATTACHMENTS = 2
DATA_FLAGS = 4
DATA_PROFILE_KEY = 6
DATA_TIMESTAMP = 7
DATA_QUOTE = 8
DATA_REACTION = 11
DATA_PROFILE = 101
DATA_SYNC_TARGET = 105

QUOTE_ID = 1
QUOTE_AUTHOR = 2
QUOTE_TEXT = 3

ATTACH_ID = 1  # fixed64
ATTACH_CONTENT_TYPE = 2
ATTACH_KEY = 3
ATTACH_SIZE = 4
ATTACH_DIGEST = 6
ATTACH_FILENAME = 7
ATTACH_FLAGS = 8
ATTACH_WIDTH = 9
ATTACH_HEIGHT = 10
ATTACH_CAPTION = 11
ATTACH_URL = 101

PROFILE_DISPLAY_NAME = 1
PROFILE_PICTURE = 2
PROFILE_LAST_UPDATE = 3

# --- padding -----------------------------------------------------------------

PADDING_MULTIPLE = 160
PADDING_TERMINATOR = 0x80

SIGNATURE_BYTES = sodium.crypto_sign_BYTES  # 64
ED25519_PK_BYTES = sodium.crypto_sign_PUBLICKEYBYTES  # 32


def pad_message(payload: bytes) -> bytes:
    """Completa o payload para um multiplo de 160 bytes (terminador 0x80)."""
    size = len(payload) + 1
    size += PADDING_MULTIPLE - (size % PADDING_MULTIPLE)
    out = bytearray(size)
    out[: len(payload)] = payload
    out[len(payload)] = PADDING_TERMINATOR
    return bytes(out)


def unpad_message(payload: bytes) -> bytes:
    """Remove o padding; devolve o payload intacto se ele nao estiver padded."""
    size = len(payload)
    while size:
        ch = payload[size - 1]
        if ch != 0x00 and ch != PADDING_TERMINATOR:
            break  # padding com lixo: assume mensagem sem padding
        size -= 1
        if ch == PADDING_TERMINATOR:
            break
    return payload[:size]


# --- anexos (AttachmentPointer) ---------------------------------------------


@dataclass
class Attachment:
    """Anexo anunciado numa mensagem (o arquivo vive no file server)."""

    url: str | None = None
    content_type: str | None = None
    key: bytes | None = None  # 64 bytes: AES + HMAC
    digest: bytes | None = None
    size: int | None = None  # tamanho original, sem padding
    file_name: str | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    attachment_id: int | None = None
    local_path: str | None = None  # preenchido depois do download

    @property
    def is_image(self) -> bool:
        if self.content_type and self.content_type.lower().startswith("image/"):
            return True
        name = (self.file_name or "").lower()
        return name.endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".avif")
        )

    @property
    def descricao(self) -> str:
        partes = [self.file_name or self.content_type or t("attachment")]
        if self.size:
            partes.append(
                f"{self.size} B" if self.size < 1024 else f"{self.size / 1024:.0f} KB"
            )
        if self.width and self.height:
            partes.append(f"{self.width}x{self.height}")
        return " - ".join(partes)


def build_attachment_pointer(
    *,
    url: str,
    attachment_id: int = 0,
    content_type: str | None = None,
    key: bytes | None = None,
    digest: bytes | None = None,
    size: int | None = None,
    file_name: str | None = None,
    width: int | None = None,
    height: int | None = None,
    caption: str | None = None,
) -> bytes:
    out = proto.f_fixed64(ATTACH_ID, attachment_id)  # required pelo .proto
    if content_type:
        out += proto.f_string(ATTACH_CONTENT_TYPE, content_type)
    if key:
        out += proto.f_bytes(ATTACH_KEY, key)
    if size:
        out += proto.f_uint64(ATTACH_SIZE, size)
    if digest:
        out += proto.f_bytes(ATTACH_DIGEST, digest)
    if file_name:
        out += proto.f_string(ATTACH_FILENAME, file_name)
    if width:
        out += proto.f_uint64(ATTACH_WIDTH, width)
    if height:
        out += proto.f_uint64(ATTACH_HEIGHT, height)
    if caption:
        out += proto.f_string(ATTACH_CAPTION, caption)
    out += proto.f_string(ATTACH_URL, url)
    return out


def parse_attachment_pointer(raw: bytes) -> Attachment:
    fields = proto.decode(raw)
    id_raw = proto.get(fields, ATTACH_ID)
    key = proto.get(fields, ATTACH_KEY)
    digest = proto.get(fields, ATTACH_DIGEST)
    return Attachment(
        url=proto.get_str(fields, ATTACH_URL),
        content_type=proto.get_str(fields, ATTACH_CONTENT_TYPE),
        key=bytes(key) if isinstance(key, (bytes, bytearray)) else None,
        digest=bytes(digest) if isinstance(digest, (bytes, bytearray)) else None,
        size=proto.get(fields, ATTACH_SIZE),
        file_name=proto.get_str(fields, ATTACH_FILENAME),
        width=proto.get(fields, ATTACH_WIDTH),
        height=proto.get(fields, ATTACH_HEIGHT),
        caption=proto.get_str(fields, ATTACH_CAPTION),
        attachment_id=(
            int.from_bytes(id_raw, "little")
            if isinstance(id_raw, (bytes, bytearray)) and len(id_raw) == 8
            else None
        ),
    )


# --- Content (protobuf) ------------------------------------------------------


def build_content(
    *,
    body: str | None = None,
    timestamp_ms: int,
    display_name: str | None = None,
    profile_picture: str | None = None,
    sync_target: str | None = None,
    typing: int | None = None,
    attachments: list[bytes] | None = None,
) -> bytes:
    """Serializa um `Content` com um `DataMessage` de texto.

    `typing`, quando dado, troca o DataMessage por um TypingMessage
    (0 = comecou a digitar, 1 = parou).
    """
    out = b""

    if typing is not None:
        typing_msg = proto.f_uint64(1, timestamp_ms) + proto.f_uint64(2, typing)
        out += proto.f_message(CONTENT_TYPING_MESSAGE, typing_msg)
    else:
        data = b""
        if body is not None:
            data += proto.f_string(DATA_BODY, body)
        for pointer in attachments or []:
            data += proto.f_message(DATA_ATTACHMENTS, pointer)
        data += proto.f_uint64(DATA_TIMESTAMP, timestamp_ms)
        if display_name is not None or profile_picture is not None:
            profile = b""
            if display_name is not None:
                profile += proto.f_string(PROFILE_DISPLAY_NAME, display_name)
            if profile_picture is not None:
                profile += proto.f_string(PROFILE_PICTURE, profile_picture)
            data += proto.f_message(DATA_PROFILE, profile)
        if sync_target is not None:
            data += proto.f_string(DATA_SYNC_TARGET, sync_target)
        out += proto.f_message(CONTENT_DATA_MESSAGE, data)

    # sigTimestamp autentica o horario de envio (fica dentro da caixa selada).
    out += proto.f_uint64(CONTENT_SIG_TIMESTAMP, timestamp_ms)
    return out


# --- criptografia 1-para-1 ---------------------------------------------------


def sign_for_recipient(
    ed25519_sk: bytes, ed25519_pk: bytes, recipient_x25519_pk: bytes, message: bytes
) -> bytes:
    """mensagem || pubkey_ed25519 || assinatura (ver `sign_for_recipient` em C++)."""
    verification = message + ed25519_pk + recipient_x25519_pk
    signature = keys.sign_detached(verification, ed25519_sk)
    return message + ed25519_pk + signature


def encrypt_for_recipient(
    identity: keys.Identity, recipient_x25519_pk: bytes, message: bytes
) -> bytes:
    """Caixa selada (anonima) com a mensagem assinada dentro."""
    signed = sign_for_recipient(
        identity.ed25519_sk, identity.ed25519_pk, recipient_x25519_pk, message
    )
    return sodium.crypto_box_seal(signed, recipient_x25519_pk)


def decrypt_from_sender(identity: keys.Identity, ciphertext: bytes) -> tuple[bytes, bytes]:
    """Abre a caixa selada e confere a assinatura.

    Devolve (plaintext_sem_padding, pubkey_ed25519_do_remetente).
    """
    signed = sodium.crypto_box_seal_open(ciphertext, identity.x25519_pk, identity.x25519_sk)
    if len(signed) < ED25519_PK_BYTES + SIGNATURE_BYTES:
        raise ValueError(t("decrypted message too short"))

    signature = signed[-SIGNATURE_BYTES:]
    sender_ed_pk = signed[-(SIGNATURE_BYTES + ED25519_PK_BYTES) : -SIGNATURE_BYTES]
    message = signed[: -(SIGNATURE_BYTES + ED25519_PK_BYTES)]

    verification = message + sender_ed_pk + identity.x25519_pk
    if not keys.verify_detached(verification, signature, sender_ed_pk):
        raise ValueError(t("invalid sender signature"))

    return unpad_message(message), sender_ed_pk


def _pro_sig_decoy(content: bytes) -> bytes:
    """Assinatura `proSig` chamariz, com chave descartavel.

    Os clientes atuais sempre preenchem `proSig` -- com assinatura real (Session
    Pro) ou com um valor valido na forma mas que nao verifica contra nada --
    para que mensagens pro e nao-pro sejam indistinguiveis na rede. Ninguem
    verifica esse campo quando nao ha `ProMessage` no Content.
    """
    _, throwaway_sk = sodium.crypto_sign_seed_keypair(random_bytes(32))
    return keys.sign_detached(content, throwaway_sk)


# --- Envelope + WebSocketMessage --------------------------------------------


def build_envelope(
    ciphertext: bytes, timestamp_ms: int, *, pro_sig: bytes | None = None
) -> bytes:
    out = proto.f_uint64(ENVELOPE_TYPE, ENVELOPE_TYPE_SESSION_MESSAGE)
    out += proto.f_uint64(ENVELOPE_TIMESTAMP, timestamp_ms)
    out += proto.f_uint64(ENVELOPE_SOURCE_DEVICE, 1)
    out += proto.f_bytes(ENVELOPE_CONTENT, ciphertext)
    if pro_sig is not None:
        out += proto.f_bytes(ENVELOPE_PRO_SIG, pro_sig)
    return out


def wrap_websocket(envelope: bytes) -> bytes:
    """Envelope dentro de um WebSocketMessage REQUEST (verb/path vazios)."""
    request = (
        proto.f_string(WS_REQ_VERB, "")
        + proto.f_string(WS_REQ_PATH, "")
        + proto.f_bytes(WS_REQ_BODY, envelope)
        + proto.f_uint64(WS_REQ_ID, 0)
    )
    return proto.f_uint64(WS_TYPE, WS_TYPE_REQUEST) + proto.f_message(WS_REQUEST, request)


def encode_outgoing(
    identity: keys.Identity,
    recipient_x25519_pk: bytes,
    content: bytes,
    timestamp_ms: int,
    *,
    with_pro_sig: bool = True,
) -> bytes:
    """Content em claro -> bytes prontos para o campo `data` do `store`."""
    ciphertext = encrypt_for_recipient(identity, recipient_x25519_pk, pad_message(content))
    pro_sig = _pro_sig_decoy(ciphertext) if with_pro_sig else None
    return wrap_websocket(build_envelope(ciphertext, timestamp_ms, pro_sig=pro_sig))


# --- decodificacao de mensagens recebidas ------------------------------------


@dataclass
class IncomingMessage:
    """Mensagem recebida do swarm, ja decifrada."""

    sender: str  # Session ID do remetente (05...)
    sender_ed25519: str  # hex da pubkey Ed25519
    timestamp_ms: int  # horario de envio informado pelo remetente
    kind: str  # text | typing | unsend | reaction | empty | outro
    body: str | None = None
    display_name: str | None = None
    hash: str | None = None  # hash da mensagem no snode
    stored_at_ms: int | None = None  # horario registrado pelo snode
    expires_at_ms: int | None = None
    is_sync: bool = False  # mensagem que o proprio remetente mandou pra si
    attachments: list[Attachment] = field(default_factory=list)
    content: dict[int, list] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def unwrap_envelope(raw: bytes) -> dict[int, list]:
    """Aceita WebSocketMessage (padrao) ou um Envelope cru."""
    fields = proto.decode(raw)
    msg_type = proto.get(fields, WS_TYPE)
    if msg_type == WS_TYPE_REQUEST and WS_REQUEST in fields:
        request = proto.get_msg(fields, WS_REQUEST) or {}
        body = proto.get(request, WS_REQ_BODY)
        if not isinstance(body, (bytes, bytearray)):
            raise ValueError(t("WebSocketMessage without a body"))
        return proto.decode(bytes(body))
    if msg_type in (ENVELOPE_TYPE_SESSION_MESSAGE, ENVELOPE_TYPE_CLOSED_GROUP_MESSAGE):
        return fields
    raise ValueError(t("payload is neither a WebSocketMessage nor an Envelope"))


def parse_content(content: dict[int, list]) -> dict[str, Any]:
    """Extrai os campos que este cliente sabe exibir."""
    out: dict[str, Any] = {"kind": "outro", "body": None, "display_name": None}

    data = proto.get_msg(content, CONTENT_DATA_MESSAGE)
    typing = proto.get_msg(content, CONTENT_TYPING_MESSAGE)
    unsend = proto.get_msg(content, CONTENT_UNSEND_REQUEST)

    if data is not None:
        body = proto.get_str(data, DATA_BODY)
        reaction = proto.get_msg(data, DATA_REACTION)
        profile = proto.get_msg(data, DATA_PROFILE)
        if profile:
            out["display_name"] = proto.get_str(profile, PROFILE_DISPLAY_NAME)
        quote = proto.get_msg(data, DATA_QUOTE)
        if quote:
            out["quote"] = {
                "id": proto.get(quote, QUOTE_ID),
                "author": proto.get_str(quote, QUOTE_AUTHOR),
                "text": proto.get_str(quote, QUOTE_TEXT),
            }
        attachments = [
            parse_attachment_pointer(bytes(raw))
            for raw in data.get(DATA_ATTACHMENTS, [])
            if isinstance(raw, (bytes, bytearray))
        ]
        if attachments:
            out["attachments"] = attachments
        sync_target = proto.get_str(data, DATA_SYNC_TARGET)
        if sync_target:
            out["sync_target"] = sync_target

        if body:
            out["kind"] = "text"
            out["body"] = body
        elif reaction is not None:
            out["kind"] = "reaction"
            out["body"] = proto.get_str(reaction, 3)  # emoji
        elif attachments:
            out["kind"] = "anexo"
        else:
            out["kind"] = "empty"
    elif typing is not None:
        out["kind"] = "typing"
        out["body"] = t("stopped typing") if proto.get(typing, 2) else t("is typing...")
    elif unsend is not None:
        out["kind"] = "unsend"

    timer = proto.get(content, CONTENT_EXPIRATION_TIMER)
    if timer:
        out["expiration_timer"] = timer
    return out


def decode_incoming(
    identity: keys.Identity,
    raw: bytes,
    *,
    hash_: str | None = None,
    stored_at_ms: int | None = None,
    expires_at_ms: int | None = None,
) -> IncomingMessage:
    """Payload cru do snode -> `IncomingMessage` decifrada e verificada."""
    envelope = unwrap_envelope(raw)

    env_type = proto.get(envelope, ENVELOPE_TYPE)
    if env_type != ENVELOPE_TYPE_SESSION_MESSAGE:
        raise ValueError(t("envelope type {type} not supported (1-to-1 only)", type=env_type))

    ciphertext = proto.get(envelope, ENVELOPE_CONTENT)
    if not isinstance(ciphertext, (bytes, bytearray)):
        raise ValueError(t("envelope without content"))

    plaintext, sender_ed_pk = decrypt_from_sender(identity, bytes(ciphertext))
    content = proto.decode(plaintext) if plaintext else {}
    parsed = parse_content(content)

    timestamp = (
        proto.get(content, CONTENT_SIG_TIMESTAMP)
        or proto.get(envelope, ENVELOPE_TIMESTAMP)
        or 0
    )
    sender = keys.session_id_from_ed25519(sender_ed_pk)

    return IncomingMessage(
        sender=sender,
        sender_ed25519=sender_ed_pk.hex(),
        timestamp_ms=int(timestamp),
        kind=parsed["kind"],
        body=parsed["body"],
        display_name=parsed["display_name"],
        hash=hash_,
        stored_at_ms=stored_at_ms,
        expires_at_ms=expires_at_ms,
        is_sync=sender == identity.session_id,
        attachments=parsed.get("attachments") or [],
        content=content,
        extra={
            k: v
            for k, v in parsed.items()
            if k not in ("kind", "body", "display_name", "attachments")
        },
    )
