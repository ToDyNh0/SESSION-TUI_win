"""Cliente Session de alto nivel: abrir conta, enviar e receber mensagens."""

from __future__ import annotations

import hashlib
import mimetypes
import re
import time
from base64 import b64decode, b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import attachments as att
from . import keys, killswitch, wire
from .i18n import t
from .keys import Identity
from .profile import HistoryEntry, Profile
from .snode import NAMESPACE_DEFAULT, SnodeError, SnodeNetwork
from .wire import Attachment, IncomingMessage

CLOCK_RESYNC_S = 10 * 60
SEEN_HASHES_MAX = 2000
NOME_SEGURO = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class SendResult:
    session_id: str
    timestamp_ms: int
    accepted: int  # quantos nos da swarm guardaram a mensagem
    swarm_size: int
    hash: str | None
    size_bytes: int
    hash_matches: bool | None = None  # o no guardou exatamente os bytes enviados?
    attachment_bytes: int | None = None  # tamanho cifrado enviado ao file server
    attachment_url: str | None = None

    @property
    def ok(self) -> bool:
        return self.accepted > 0


class SessionClient:
    """Une identidade, rede e perfil em uma interface simples."""

    def __init__(
        self,
        identity: Identity,
        network: SnodeNetwork,
        profile: Profile | None = None,
        *,
        log: Callable[[str], None] | None = None,
        file_server: att.FileServer | None = None,
    ) -> None:
        self.identity = identity
        self.network = network
        self.profile = profile
        self._log = log or (lambda _msg: None)
        self.files = file_server or att.FileServer(network=network, log=self._log)
        self._clock_synced_at = 0.0
        self._seen_hashes: list[str] = []
        self._seen_set: set[str] = set()

    # --- construcao ---------------------------------------------------------

    @classmethod
    def open(
        cls,
        profile_path: str | Path = "session_profile",
        *,
        use_onion: bool = False,
        create: bool = False,
        mnemonic: str | None = None,
        senha: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> "SessionClient":
        """Abre (ou cria) o perfil e devolve um cliente pronto.

        `senha` e necessaria quando a conta em disco esta protegida; na criacao,
        ja grava a conta nova protegida por ela.
        """
        profile = Profile.open(profile_path)
        if profile.has_account():
            identity = profile.load_identity(senha)
        elif mnemonic:
            identity = Identity.from_mnemonic(mnemonic)
            profile.save_identity(identity, senha)
        elif create:
            identity = Identity.generate()
            profile.save_identity(identity, senha)
        else:
            raise FileNotFoundError(
                t("no account at {path} -- create one with `new`", path=profile.path)
            )

        killswitch.registrar_acesso(profile, forcar=True)
        network = SnodeNetwork(
            use_onion=use_onion, cache_path=profile.snodes_path, log=log
        )
        return cls(identity, network, profile, log=log)

    # --- propriedades -------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self.identity.session_id

    @property
    def display_name(self) -> str | None:
        return self.profile.display_name if self.profile else None

    def _ensure_clock(self) -> None:
        if time.time() - self._clock_synced_at > CLOCK_RESYNC_S:
            try:
                self.network.sync_clock()
                self._clock_synced_at = time.time()
            except SnodeError as exc:
                self._log(t("could not sync the clock: {error}", error=exc))

    # --- envio --------------------------------------------------------------

    def send_text(
        self, session_id: str, text: str, *, timestamp_ms: int | None = None
    ) -> SendResult:
        """Envia uma mensagem de texto para um Session ID."""
        recipient_pk = keys.parse_session_id(session_id)
        self._ensure_clock()
        timestamp = timestamp_ms or self.network.now_ms()

        content = wire.build_content(
            body=text, timestamp_ms=timestamp, display_name=self.display_name
        )
        payload = wire.encode_outgoing(self.identity, recipient_pk, content, timestamp)
        result = self.network.store(session_id, payload, timestamp_ms=timestamp)

        if self.profile:
            self.profile.append_history(
                HistoryEntry(
                    direction="out",
                    peer=session_id,
                    timestamp_ms=timestamp,
                    body=text,
                    kind="text",
                    display_name=self.display_name,
                    hash=result.get("hash"),
                )
            )
        returned_hash = result.get("hash")
        return SendResult(
            session_id=session_id,
            timestamp_ms=timestamp,
            accepted=result["accepted"],
            swarm_size=result["swarm_size"],
            hash=returned_hash,
            size_bytes=len(payload),
            hash_matches=(
                returned_hash == self.expected_message_hash(session_id, payload)
                if returned_hash
                else None
            ),
        )

    def send_file(
        self,
        session_id: str,
        path: str | Path,
        *,
        caption: str | None = None,
        timestamp_ms: int | None = None,
    ) -> SendResult:
        """Envia um arquivo (imagem ou qualquer outro) como anexo.

        O arquivo e cifrado com uma chave propria, enviado ao file server do
        Session e anunciado na mensagem por uma AttachmentPointer -- o servidor
        guarda apenas bytes cifrados, e a chave vai dentro da mensagem.
        """
        recipient_pk = keys.parse_session_id(session_id)
        arquivo = Path(path).expanduser()
        if not arquivo.is_file():
            raise FileNotFoundError(t("file not found: {path}", path=arquivo))
        dados = arquivo.read_bytes()
        if not dados:
            raise att.AttachmentError(t("empty file"))

        content_type = att.guess_content_type(arquivo)
        cifrado = att.encrypt_attachment(dados)
        enviado = self.files.upload(cifrado.blob)
        largura, altura = (
            att.image_dimensions(dados) if att.is_image(content_type, arquivo.name) else (None, None)
        )

        pointer = wire.build_attachment_pointer(
            url=enviado.url,
            attachment_id=int(enviado.file_id) if enviado.file_id.isdigit() else 0,
            content_type=content_type,
            key=cifrado.key,
            digest=cifrado.digest,
            size=cifrado.plain_size,
            file_name=arquivo.name,
            width=largura,
            height=altura,
        )

        self._ensure_clock()
        timestamp = timestamp_ms or self.network.now_ms()
        content = wire.build_content(
            body=caption,
            timestamp_ms=timestamp,
            display_name=self.display_name,
            attachments=[pointer],
        )
        payload = wire.encode_outgoing(self.identity, recipient_pk, content, timestamp)
        result = self.network.store(session_id, payload, timestamp_ms=timestamp)

        if self.profile:
            self.profile.append_history(
                HistoryEntry(
                    direction="out",
                    peer=session_id,
                    timestamp_ms=timestamp,
                    body=caption,
                    kind="imagem" if att.is_image(content_type, arquivo.name) else "anexo",
                    display_name=self.display_name,
                    hash=result.get("hash"),
                    attachment=str(arquivo),
                )
            )

        returned_hash = result.get("hash")
        return SendResult(
            session_id=session_id,
            timestamp_ms=timestamp,
            accepted=result["accepted"],
            swarm_size=result["swarm_size"],
            hash=returned_hash,
            size_bytes=len(payload),
            hash_matches=(
                returned_hash == self.expected_message_hash(session_id, payload)
                if returned_hash
                else None
            ),
            attachment_bytes=len(cifrado.blob),
            attachment_url=enviado.url,
        )

    def send_typing(self, session_id: str, *, stopped: bool = False) -> None:
        """Aviso de 'digitando...' (o app oficial mostra isso na conversa)."""
        recipient_pk = keys.parse_session_id(session_id)
        self._ensure_clock()
        timestamp = self.network.now_ms()
        content = wire.build_content(timestamp_ms=timestamp, typing=1 if stopped else 0)
        payload = wire.encode_outgoing(self.identity, recipient_pk, content, timestamp)
        self.network.store(session_id, payload, ttl_ms=20_000, timestamp_ms=timestamp)

    # --- recebimento --------------------------------------------------------

    def _nome_seguro(self, message: IncomingMessage, anexo: Attachment, indice: int) -> str:
        """Nome de arquivo previsivel e sem surpresas.

        O nome vem do remetente, entao nada de barras, `..` ou nomes gigantes:
        so o nome puro, com caracteres estranhos trocados por `_`.
        """
        bruto = Path(anexo.file_name or "").name
        limpo = NOME_SEGURO.sub("_", bruto).strip("._") or f"anexo{indice}"
        if "." not in limpo and anexo.content_type:
            limpo += mimetypes.guess_extension(anexo.content_type) or ""
        return f"{message.timestamp_ms}_{message.sender[2:10]}_{limpo[:80]}"

    def fetch_attachments(self, message: IncomingMessage) -> list[Attachment]:
        """Baixa, verifica e salva os anexos de uma mensagem recebida."""
        salvos: list[Attachment] = []
        for indice, anexo in enumerate(message.attachments):
            if not anexo.url:
                continue
            if not anexo.key:
                self._log(t("attachment without a key (cannot decrypt); skipping"))
                continue
            if anexo.size and anexo.size > att.MAX_ATTACHMENT_SIZE:
                self._log(t("attachment too large ({n} B); skipping", n=anexo.size))
                continue
            try:
                blob = self.files.download(anexo.url)
                dados = att.decrypt_any(
                    blob, anexo.key, digest=anexo.digest, size=anexo.size
                )
            except att.AttachmentError as exc:
                self._log(t("attachment not downloaded: {error}", error=exc))
                continue

            if self.profile:
                destino = self.profile.attachments_dir / self._nome_seguro(message, anexo, indice)
                try:
                    destino.write_bytes(dados)
                    anexo.local_path = str(destino)
                except OSError as exc:
                    self._log(t("could not save the attachment: {error}", error=exc))
            salvos.append(anexo)
        return salvos

    def poll(
        self, *, namespace: int = NAMESPACE_DEFAULT, download_attachments: bool = True
    ) -> list[IncomingMessage]:
        """Busca novas mensagens na propria swarm e as decifra."""
        if self.profile:
            killswitch.registrar_acesso(self.profile)  # usar a conta conta como acesso
        self._ensure_clock()
        last_hash = self.profile.last_hash(namespace) if self.profile else None
        result = self.network.retrieve(self.identity, namespace=namespace, last_hash=last_hash)

        messages: list[IncomingMessage] = []
        newest_hash = None
        for raw in result["messages"]:
            msg_hash = raw.get("hash")
            newest_hash = msg_hash or newest_hash
            if msg_hash and msg_hash in self._seen_set:
                continue
            data = raw.get("data")
            if not data:
                continue
            try:
                message = wire.decode_incoming(
                    self.identity,
                    b64decode(data),
                    hash_=msg_hash,
                    stored_at_ms=raw.get("timestamp"),
                    expires_at_ms=raw.get("expiry"),
                )
            except Exception as exc:  # mensagem de outro formato, grupo, config...
                self._log(t("ignoring message {hash}: {error}", hash=str(msg_hash)[:8], error=exc))
                continue

            self._remember(msg_hash)
            if download_attachments and message.attachments:
                self.fetch_attachments(message)
            messages.append(message)

            if self.profile and message.kind in ("text", "reaction", "anexo"):
                primeiro = message.attachments[0] if message.attachments else None
                self.profile.append_history(
                    HistoryEntry(
                        direction="in",
                        peer=message.sender,
                        timestamp_ms=message.timestamp_ms,
                        body=message.body,
                        kind=(
                            "imagem"
                            if primeiro is not None and primeiro.is_image
                            else message.kind
                        ),
                        display_name=message.display_name,
                        hash=message.hash,
                        attachment=primeiro.local_path if primeiro else None,
                    )
                )

        if self.profile and newest_hash:
            self.profile.set_last_hash(newest_hash, namespace)
        return messages

    def _remember(self, msg_hash: str | None) -> None:
        if not msg_hash:
            return
        self._seen_set.add(msg_hash)
        self._seen_hashes.append(msg_hash)
        if len(self._seen_hashes) > SEEN_HASHES_MAX:
            old = self._seen_hashes.pop(0)
            self._seen_set.discard(old)

    # --- diagnostico --------------------------------------------------------

    @staticmethod
    def expected_message_hash(session_id: str, data: bytes, namespace: int = 0) -> str:
        """Hash que o snode deve calcular: blake2b(PUBKEY || NAMESPACE || DATA).

        Serve para confirmar que o no guardou exatamente os bytes enviados.
        """
        pubkey = bytes([0x05]) + keys.parse_session_id(session_id)
        ns = b"" if namespace == 0 else str(namespace).encode()
        digest = hashlib.blake2b(pubkey + ns + data, digest_size=32).digest()
        return b64encode(digest).decode("ascii").rstrip("=")
