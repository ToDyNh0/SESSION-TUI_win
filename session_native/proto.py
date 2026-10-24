"""Protobuf (proto2) minimo -- apenas o necessario para o Session.

Evita a dependencia de `protobuf`/`protoc`: o Session usa poucos campos e o
formato wire do protobuf e simples. Os numeros de campo usados pelo projeto
vem de `proto/SessionProtos.proto` e `proto/WebSocketResources.proto` da
libsession-util.
"""

from __future__ import annotations

from .i18n import t

WIRE_VARINT = 0
WIRE_64BIT = 1
WIRE_LEN = 2
WIRE_32BIT = 5


def varint(value: int) -> bytes:
    """Codifica um inteiro em varint (base 128, little endian)."""
    if value < 0:
        value += 1 << 64  # complemento de dois, como o protobuf faz
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _tag(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def f_uint64(field: int, value: int) -> bytes:
    """Campo varint: uint64, uint32, enum ou bool."""
    return _tag(field, WIRE_VARINT) + varint(value)


def f_fixed64(field: int, value: int) -> bytes:
    """Campo de 64 bits fixos, little endian (ex.: AttachmentPointer.id)."""
    return _tag(field, WIRE_64BIT) + int(value).to_bytes(8, "little", signed=False)


def f_bytes(field: int, value: bytes) -> bytes:
    """Campo com tamanho delimitado: bytes, string ou sub-mensagem."""
    return _tag(field, WIRE_LEN) + varint(len(value)) + value


def f_string(field: int, value: str) -> bytes:
    return f_bytes(field, value.encode("utf-8"))


f_message = f_bytes


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """Le um varint em `pos`; devolve (valor, nova_posicao)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError(t("truncated varint"))
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError(t("varint too long"))


def decode(buf: bytes) -> dict[int, list]:
    """Decodifica uma mensagem em {numero_do_campo: [valores...]}.

    varint -> int, delimitado -> bytes, 32/64 bits -> bytes crus.
    Campos repetidos (ou duplicados) aparecem na ordem em que vieram.
    """
    fields: dict[int, list] = {}
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        field, wire = key >> 3, key & 0x07
        if wire == WIRE_VARINT:
            value, pos = read_varint(buf, pos)
        elif wire == WIRE_LEN:
            length, pos = read_varint(buf, pos)
            if pos + length > len(buf):
                raise ValueError(t("truncated length-delimited field"))
            value = buf[pos : pos + length]
            pos += length
        elif wire == WIRE_64BIT:
            value = buf[pos : pos + 8]
            pos += 8
        elif wire == WIRE_32BIT:
            value = buf[pos : pos + 4]
            pos += 4
        else:
            raise ValueError(t("unknown wire type: {wire}", wire=wire))
        fields.setdefault(field, []).append(value)
    return fields


def get(fields: dict[int, list], field: int, default=None):
    """Primeiro valor de um campo (ou `default`)."""
    values = fields.get(field)
    return values[0] if values else default


def get_str(fields: dict[int, list], field: int, default=None):
    raw = get(fields, field)
    if not isinstance(raw, (bytes, bytearray)):
        return default
    return bytes(raw).decode("utf-8", "replace")


def get_msg(fields: dict[int, list], field: int) -> dict[int, list] | None:
    """Decodifica uma sub-mensagem, se presente e bem formada."""
    raw = get(fields, field)
    if not isinstance(raw, (bytes, bytearray)):
        return None
    try:
        return decode(bytes(raw))
    except ValueError:
        return None
