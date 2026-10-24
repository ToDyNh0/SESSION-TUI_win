"""Cliente Session nativo em Python (Session Protocol v2, mensagens 1-para-1).

Implementa, sem depender do aplicativo oficial:

* geracao de conta (Ed25519/X25519 + frase de recuperacao de 13 palavras);
* descoberta de service nodes e da swarm do destinatario;
* criptografia ponta a ponta (caixa selada assinada, padding de 160 bytes);
* envio (`store`) e recebimento (`retrieve`) nos snodes, direto ou via onion;
* kill switch: apaga a conta depois de um tempo sem acesso.
"""

from .attachments import AttachmentError, FileServer
from .client import SendResult, SessionClient
from .keys import Identity, InvalidSessionID, parse_session_id
from .profile import HistoryEntry, Profile
from .snode import SnodeError, SnodeNetwork
from .wire import Attachment, IncomingMessage

__all__ = [
    "Attachment",
    "AttachmentError",
    "FileServer",
    "HistoryEntry",
    "Identity",
    "IncomingMessage",
    "InvalidSessionID",
    "Profile",
    "SendResult",
    "SessionClient",
    "SnodeError",
    "SnodeNetwork",
    "parse_session_id",
]

__version__ = "1.1.0"
