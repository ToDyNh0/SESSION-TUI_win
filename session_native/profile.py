"""Perfil em disco: conta, estado de sincronizacao e historico local.

Estrutura da pasta do perfil (padrao: a pasta de dados do usuario, veja
`sistema.pasta_perfil_padrao`):

    account.json   seed da conta  <-- CHAVE PRIVADA, guarde com cuidado
    state.json     last_hash do polling, contatos, nome de exibicao
    config.json    idioma, kill switch e ultimo acesso (sobrevive ao apagar tudo)
    snodes.json    cache da lista de service nodes
    history.jsonl  historico local das conversas (texto em claro)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import cofre, sistema
from .i18n import t
from .keys import Identity

ACCOUNT_FILE = "account.json"
STATE_FILE = "state.json"
CONFIG_FILE = "config.json"
SNODES_FILE = "snodes.json"
HISTORY_FILE = "history.jsonl"
ATTACHMENTS_DIR = "attachments"
SENT_DIR = "enviados"
HISTORY_MAX_LINES = 20_000


@dataclass
class HistoryEntry:
    direction: str  # "in" ou "out"
    peer: str  # Session ID do outro lado
    timestamp_ms: int
    body: str | None = None
    kind: str = "text"
    display_name: str | None = None
    hash: str | None = None
    attachment: str | None = None  # caminho local do arquivo, quando houver

    def to_dict(self) -> dict:
        return {
            "dir": self.direction,
            "peer": self.peer,
            "ts": self.timestamp_ms,
            "body": self.body,
            "kind": self.kind,
            "name": self.display_name,
            "hash": self.hash,
            "att": self.attachment,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "HistoryEntry":
        return cls(
            direction=raw.get("dir", "in"),
            peer=raw.get("peer", ""),
            timestamp_ms=int(raw.get("ts") or 0),
            body=raw.get("body"),
            kind=raw.get("kind", "text"),
            display_name=raw.get("name"),
            hash=raw.get("hash"),
            attachment=raw.get("att"),
        )


def _triturar(alvo: Path) -> None:
    """Sobrescreve o arquivo com bytes aleatorios antes de apagar (melhor esforco).

    Em SSD, sistema de arquivos com copia ou pasta sincronizada na nuvem isso
    nao garante nada -- mas no disco comum evita que o conteudo fique la
    inteiro esperando um programa de recuperacao.
    """
    try:
        tamanho = alvo.stat().st_size
        with alvo.open("r+b") as arquivo:
            arquivo.write(os.urandom(tamanho))
            arquivo.flush()
            os.fsync(arquivo.fileno())
    except OSError:
        pass


@dataclass
class Profile:
    """Pasta de perfil com a conta e os dados locais."""

    path: Path
    state: dict = field(default_factory=dict)

    @classmethod
    def open(cls, path: str | os.PathLike) -> "Profile":
        profile = cls(path=Path(path))
        sistema.preparar_pasta_privada(profile.path)
        profile.state = profile._read_json(STATE_FILE, default={})
        return profile

    # --- arquivos -----------------------------------------------------------

    @property
    def account_path(self) -> Path:
        return self.path / ACCOUNT_FILE

    @property
    def snodes_path(self) -> Path:
        return self.path / SNODES_FILE

    @property
    def history_path(self) -> Path:
        return self.path / HISTORY_FILE

    @property
    def attachments_dir(self) -> Path:
        """Pasta dos anexos recebidos (criada na hora do primeiro download)."""
        pasta = self.path / ATTACHMENTS_DIR
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _read_json(self, name: str, default):
        # utf-8-sig: aceita o BOM que o Bloco de Notas/PowerShell poem na frente
        try:
            return json.loads((self.path / name).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return default

    def _write_json(self, name: str, payload) -> None:
        target = self.path / name
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        # antivirus e sincronizadores (OneDrive...) seguram o arquivo por um
        # instante no Windows; uma segunda tentativa costuma bastar
        for tentativa in range(5):
            try:
                tmp.replace(target)
                return
            except PermissionError:
                if tentativa == 4:
                    raise
                time.sleep(0.1 * (tentativa + 1))

    # --- configuracao (idioma, kill switch) ---------------------------------

    def ler_config(self) -> dict:
        """config.json lido do disco na hora (o agendador pode ter mexido)."""
        bruto = self._read_json(CONFIG_FILE, default={})
        return bruto if isinstance(bruto, dict) else {}

    def atualizar_config(self, **campos) -> dict:
        config = self.ler_config()
        config.update(campos)
        self._write_json(CONFIG_FILE, config)
        return config

    # --- conta --------------------------------------------------------------

    def has_account(self) -> bool:
        return self.account_path.exists()

    def is_protected(self) -> bool:
        """A conta em disco esta cifrada por senha?"""
        return cofre.esta_protegido(self._read_json(ACCOUNT_FILE, default={}) or {})

    def account_session_id(self) -> str | None:
        """Session ID gravado no arquivo (fica em claro mesmo protegido)."""
        raw = self._read_json(ACCOUNT_FILE, default=None)
        return raw.get("session_id") if isinstance(raw, dict) else None

    def load_identity(self, senha: str | None = None) -> Identity:
        raw = self._read_json(ACCOUNT_FILE, default=None)
        if not isinstance(raw, dict):
            raise FileNotFoundError(t("account not found at {path}", path=self.account_path))
        if cofre.esta_protegido(raw):
            raw = cofre.abrir(raw, senha)  # levanta SenhaNecessaria / SenhaErrada
        if "seed" not in raw:
            raise FileNotFoundError(t("invalid account at {path}", path=self.account_path))
        return Identity.from_seed(bytes.fromhex(raw["seed"]))

    def save_identity(self, identity: Identity, senha: str | None = None) -> None:
        """Grava a conta. Com `senha`, o seed vai cifrado (Argon2id + XChaCha20)."""
        segredo = {
            "seed": identity.seed.hex(),
            "mnemonic": identity.mnemonic,
            "created_at": int(time.time()),
        }
        publico = {"session_id": identity.session_id}
        if senha:
            conteudo = cofre.proteger(segredo, senha, publico=publico)
        else:
            conteudo = {
                **segredo,
                **publico,
                "aviso": "this file contains the account's private key IN CLEAR TEXT",
            }
        self._write_json(ACCOUNT_FILE, conteudo)
        sistema.restringir_arquivo(self.account_path)

    def set_password(self, nova: str | None, atual: str | None = None) -> None:
        """Liga, troca ou tira a protecao por senha da conta."""
        identidade = self.load_identity(atual)
        self.save_identity(identidade, nova or None)

    def apagar_tudo(self, *, triturar: bool = True) -> list[str]:
        """Apaga conta, estado, historico, cache e anexos deste perfil.

        Remove apenas os arquivos e pastas que o proprio perfil cria -- nunca a
        pasta inteira -- para que apontar `--profile` para um lugar compartilhado
        nao vire uma tragedia. `config.json` (idioma, kill switch) fica. Nao tem
        volta: sem a frase de recuperacao a conta se perde.
        """
        import shutil

        apagados: list[str] = []
        for nome in (ACCOUNT_FILE, STATE_FILE, SNODES_FILE, HISTORY_FILE):
            alvo = self.path / nome
            if alvo.exists():
                if triturar and nome != SNODES_FILE:
                    _triturar(alvo)
                try:
                    alvo.unlink()
                    apagados.append(nome)
                except OSError:
                    pass
        for pasta in (ATTACHMENTS_DIR, SENT_DIR):
            alvo = self.path / pasta
            if alvo.is_dir():
                if triturar:
                    for arquivo in alvo.rglob("*"):
                        if arquivo.is_file():
                            _triturar(arquivo)
                try:
                    shutil.rmtree(alvo)
                    apagados.append(f"{pasta}/")
                except OSError:
                    pass
        self.state = {}
        return apagados

    # --- estado -------------------------------------------------------------

    def save_state(self) -> None:
        self._write_json(STATE_FILE, self.state)

    @property
    def display_name(self) -> str | None:
        return self.state.get("display_name")

    @display_name.setter
    def display_name(self, value: str | None) -> None:
        self.state["display_name"] = value
        self.save_state()

    def last_hash(self, namespace: int = 0) -> str | None:
        return (self.state.get("last_hash") or {}).get(str(namespace))

    def set_last_hash(self, value: str | None, namespace: int = 0) -> None:
        if not value:
            return
        self.state.setdefault("last_hash", {})[str(namespace)] = value
        self.save_state()

    @property
    def contacts(self) -> list[str]:
        return list(self.state.get("contacts") or [])

    def add_contact(self, session_id: str) -> None:
        contacts = self.contacts
        if session_id not in contacts:
            contacts.append(session_id)
            self.state["contacts"] = contacts
            self.save_state()

    def conhecidos(self) -> list[str]:
        """Contatos da lista + quem aparece no historico (o CLI nao usa a lista)."""
        vistos = dict.fromkeys(self.contacts)
        for entrada in self.read_history(limit=HISTORY_MAX_LINES):
            if entrada.peer:
                vistos.setdefault(entrada.peer)
        return list(vistos)

    def remove_contact(self, session_id: str) -> None:
        contacts = [c for c in self.contacts if c != session_id]
        self.state["contacts"] = contacts
        self.save_state()

    def nickname(self, session_id: str) -> str | None:
        return (self.state.get("nicknames") or {}).get(session_id)

    def set_nickname(self, session_id: str, name: str | None) -> None:
        nicknames = self.state.setdefault("nicknames", {})
        if name:
            nicknames[session_id] = name
        else:
            nicknames.pop(session_id, None)
        self.save_state()

    # --- historico ----------------------------------------------------------

    def append_history(self, entry: HistoryEntry) -> None:
        try:
            with self.history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def read_history(self, *, peer: str | None = None, limit: int = 200) -> list[HistoryEntry]:
        try:
            lines = self.history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        entries: list[HistoryEntry] = []
        for line in lines[-HISTORY_MAX_LINES:]:
            if not line.strip():
                continue
            try:
                entry = HistoryEntry.from_dict(json.loads(line))
            except ValueError:
                continue
            if peer and entry.peer != peer:
                continue
            entries.append(entry)
        return entries[-limit:]
