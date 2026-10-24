"""Camada de rede: service nodes (snodes), swarms e os RPCs de armazenamento.

Dois transportes:

* direto  -- HTTPS para o snode (`POST /storage_rpc/v1`). Simples e rapido,
             mas o snode ve o seu IP.
* onion   -- 3 saltos cifrados em camadas (`POST /onion_req/v2` no 1o salto),
             como o aplicativo oficial faz; nenhum no ve origem e destino.

Os certificados TLS dos snodes sao autoassinados (a identidade real deles e a
chave Ed25519/X25519 publicada na blockchain do Oxen), por isso a verificacao
de certificado fica desligada -- o conteudo das mensagens e cifrado ponta a
ponta de qualquer forma.
"""

from __future__ import annotations

import json
import random
import time
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
import urllib3

from . import keys, onion
from .i18n import t
from .keys import Identity

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SEED_NODES = (
    "seed1.getsession.org:4432",
    "seed2.getsession.org:4432",
    "seed3.getsession.org:4432",
)

NAMESPACE_DEFAULT = 0  # mensagens 1-para-1
TTL_DEFAULT_MS = 14 * 24 * 60 * 60 * 1000  # 14 dias, como o cliente oficial
POOL_MIN_SIZE = 12
POOL_MAX_AGE_S = 2 * 60 * 60
MAX_MESSAGE_BODY = 76_800  # limite do snode para o campo `data`
QUARENTENA_S = 10 * 60  # quanto tempo evitar um no que falhou
TIMEOUT_CONEXAO_S = 5.0  # no morto nao merece 15 s de espera


def _motivo(exc: Exception) -> str:
    """Resume a falha numa linha legivel (o traceback do urllib3 e enorme)."""
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return t("did not respond")
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return t("took too long")
    if isinstance(exc, requests.exceptions.SSLError):
        return t("TLS error")
    if isinstance(exc, requests.exceptions.ConnectionError):
        return t("connection refused")
    texto = " ".join(str(exc).split())
    return texto[:100] if texto else type(exc).__name__


class SnodeError(RuntimeError):
    """Erro de rede ou resposta de erro de um service node."""


class SwarmChanged(SnodeError):
    """O snode respondeu 421: a swarm desse Session ID mudou."""


@dataclass(frozen=True)
class Snode:
    ip: str
    port: int
    ed25519: str
    x25519: str

    @property
    def url(self) -> str:
        return f"https://{self.ip}:{self.port}/storage_rpc/v1"

    @property
    def onion_url(self) -> str:
        return f"https://{self.ip}:{self.port}/onion_req/v2"

    @property
    def short(self) -> str:
        return f"{self.ip}:{self.port}"

    def to_dict(self) -> dict:
        return {"ip": self.ip, "port": self.port, "ed25519": self.ed25519, "x25519": self.x25519}

    @classmethod
    def from_dict(cls, raw: dict) -> "Snode":
        return cls(
            ip=str(raw["ip"]),
            port=int(raw["port"]),
            ed25519=str(raw["ed25519"]),
            x25519=str(raw["x25519"]),
        )

    @classmethod
    def from_seed_entry(cls, raw: dict) -> "Snode":
        return cls(
            ip=raw["public_ip"],
            port=int(raw["storage_port"]),
            ed25519=raw["pubkey_ed25519"],
            x25519=raw["pubkey_x25519"],
        )

    @classmethod
    def from_swarm_entry(cls, raw: dict) -> "Snode":
        return cls(
            ip=raw["ip"],
            port=int(raw.get("port_https") or raw.get("port") or 0),
            ed25519=raw["pubkey_ed25519"],
            x25519=raw["pubkey_x25519"],
        )


def _valid(node: Snode) -> bool:
    return bool(
        node.ip
        and node.ip != "0.0.0.0"
        and node.port
        and len(node.ed25519) == 64
        and len(node.x25519) == 64
    )


class SnodeNetwork:
    """Descoberta de nos, cache de swarms e chamadas RPC com retentativas."""

    def __init__(
        self,
        *,
        use_onion: bool = False,
        cache_path: Path | None = None,
        timeout: float = 15.0,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.use_onion = use_onion
        self.cache_path = cache_path
        self.timeout = timeout
        self._log = log or (lambda _msg: None)
        self.pool: list[Snode] = []
        self.pool_fetched_at = 0.0
        self._swarms: dict[str, list[Snode]] = {}
        self._quarentena: dict[str, float] = {}  # ed25519 -> quando falhou
        self._clock_offset_ms = 0
        self._http = requests.Session()
        self._http.verify = False
        self._http.headers.update({"Content-Type": "application/json"})
        self._load_pool_cache()

    # --- cache em disco ------------------------------------------------------

    def _load_pool_cache(self) -> None:
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
            nodes = [Snode.from_dict(n) for n in raw.get("nodes", [])]
            self.pool = [n for n in nodes if _valid(n)]
            self.pool_fetched_at = float(raw.get("fetched_at", 0))
        except (OSError, ValueError, KeyError):
            self.pool = []

    def _save_pool_cache(self) -> None:
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {"fetched_at": self.pool_fetched_at, "nodes": [n.to_dict() for n in self.pool]}
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # --- descoberta de nos ---------------------------------------------------

    def ensure_pool(self, *, force: bool = False) -> list[Snode]:
        """Garante uma lista de snodes utilizavel (cache ou seed nodes)."""
        fresh = time.time() - self.pool_fetched_at < POOL_MAX_AGE_S
        if not force and len(self.pool) >= POOL_MIN_SIZE and fresh:
            return self.pool
        try:
            self.pool = self._fetch_pool_from_seeds()
            self.pool_fetched_at = time.time()
            self._save_pool_cache()
            self._log(t("node list updated: {n} snodes", n=len(self.pool)))
        except SnodeError:
            if not self.pool:
                raise
            self._log(t("could not update the node list; using the cache"))
        return self.pool

    def _fetch_pool_from_seeds(self) -> list[Snode]:
        payload = {
            "jsonrpc": "2.0",
            "id": "0",
            "method": "get_n_service_nodes",
            "params": {
                "active_only": True,
                "fields": {
                    "public_ip": True,
                    "storage_port": True,
                    "pubkey_x25519": True,
                    "pubkey_ed25519": True,
                },
            },
        }
        errors = []
        for seed in random.sample(SEED_NODES, len(SEED_NODES)):
            url = f"https://{seed}/json_rpc"
            try:
                response = self._http.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                states = response.json()["result"]["service_node_states"]
            except Exception as exc:
                errors.append(f"{seed}: {exc}")
                continue
            nodes = [Snode.from_seed_entry(s) for s in states if s.get("public_ip")]
            nodes = [n for n in nodes if _valid(n)]
            if nodes:
                return nodes
            errors.append(t("{seed}: empty list", seed=seed))
        raise SnodeError(t("no seed node answered -- {errors}", errors="; ".join(errors)))

    # --- nos que falharam ----------------------------------------------------

    def marcar_falha(self, node: Snode) -> None:
        """Poe o no de molho: para de insistir em quem acabou de falhar."""
        self._quarentena[node.ed25519] = time.time()

    def _em_quarentena(self, node: Snode) -> bool:
        quando = self._quarentena.get(node.ed25519)
        if quando is None:
            return False
        if time.time() - quando > QUARENTENA_S:
            self._quarentena.pop(node.ed25519, None)
            return False
        return True

    def _saudaveis(self, nodes: list[Snode]) -> list[Snode]:
        """Os nos fora de quarentena -- ou todos, se nao sobrar ninguem."""
        livres = [n for n in nodes if not self._em_quarentena(n)]
        return livres or nodes

    def random_node(self, *, exclude: list[Snode] | None = None) -> Snode:
        pool = self.ensure_pool()
        skip = {n.ed25519 for n in (exclude or [])}
        candidates = [n for n in pool if n.ed25519 not in skip]
        if not candidates:
            raise SnodeError(t("no snodes available"))
        return random.choice(self._saudaveis(candidates))

    def build_path(self, destination: Snode) -> list[Snode]:
        """Caminho de 3 saltos distintos, sem incluir o destino."""
        pool = self.ensure_pool()
        candidates = [n for n in pool if n.ed25519 != destination.ed25519]
        if len(candidates) < onion.ONION_PATH_SIZE:
            raise SnodeError(t("not enough snodes to build an onion path"))
        return random.sample(candidates, onion.ONION_PATH_SIZE)

    # --- RPC -----------------------------------------------------------------

    def rpc(self, target: Snode, method: str, params: dict) -> dict:
        """Chama um RPC num snode, pelo transporte configurado."""
        if self.use_onion:
            return self._rpc_onion(target, method, params)
        return self._rpc_direct(target, method, params)

    def _rpc_direct(self, target: Snode, method: str, params: dict) -> dict:
        body = {"method": method, "params": params}
        try:
            response = self._http.post(
                target.url, json=body, timeout=(TIMEOUT_CONEXAO_S, self.timeout)
            )
        except requests.RequestException as exc:
            raise SnodeError(f"{target.short}: {_motivo(exc)}") from exc
        return self._handle_status(target, response.status_code, response.text)

    def _rpc_onion(self, target: Snode, method: str, params: dict) -> dict:
        path = self.build_path(target)
        built = onion.build_onion_request(path, target, method, params)
        try:
            response = self._http.post(
                path[0].onion_url,
                data=built.payload,
                headers={"Content-Type": "application/octet-stream"},
                timeout=(TIMEOUT_CONEXAO_S, self.timeout),
            )
        except requests.RequestException as exc:
            self.marcar_falha(path[0])
            raise SnodeError(
                t("onion via {node}: {reason}", node=path[0].short, reason=_motivo(exc))
            ) from exc
        if response.status_code != 200:
            raise SnodeError(
                t(
                    "onion via {node}: HTTP {code} {text}",
                    node=path[0].short,
                    code=response.status_code,
                    text=response.text[:200],
                )
            )
        try:
            return built.parse_response(response.content)
        except onion.OnionError as exc:
            raise SnodeError(t("onion via {node}: {reason}", node=path[0].short, reason=exc)) from exc

    def _handle_status(self, target: Snode, status: int, text: str) -> dict:
        if status == 200:
            try:
                return json.loads(text) if text else {}
            except ValueError as exc:
                raise SnodeError(t("{node}: non-JSON response", node=target.short)) from exc
        if status == 421:
            raise SwarmChanged(t("{node}: the swarm changed", node=target.short))
        raise SnodeError(f"{target.short}: HTTP {status} {text[:200]}")

    def rpc_any(self, method: str, params: dict, *, tries: int = 4) -> dict:
        """Chama um RPC em nos aleatorios da rede ate um responder."""
        tried: list[Snode] = []
        last: Exception | None = None
        for _ in range(tries):
            try:
                node = self.random_node(exclude=tried)
            except SnodeError:
                break
            tried.append(node)
            try:
                return self.rpc(node, method, params)
            except SnodeError as exc:
                last = exc
                self.marcar_falha(node)
                self._log(f"{method}: {exc}")
        raise SnodeError(
            t("{method} failed on {n} nodes: {last}", method=method, n=len(tried), last=last)
        )

    # --- swarm ---------------------------------------------------------------

    def get_swarm(self, session_id: str, *, force: bool = False) -> list[Snode]:
        """Snodes responsaveis por guardar as mensagens desse Session ID."""
        keys.parse_session_id(session_id)
        cached = self._swarms.get(session_id)
        if cached and not force:
            return cached
        result = self.rpc_any("get_swarm", {"pubkey": session_id})
        nodes = [Snode.from_swarm_entry(n) for n in result.get("snodes", [])]
        nodes = [n for n in nodes if _valid(n)]
        if not nodes:
            raise SnodeError(t("empty swarm for {sid}...", sid=session_id[:10]))
        self._swarms[session_id] = nodes
        return nodes

    def swarm_rpc(self, session_id: str, method: str, params: dict, *, tries: int = 3) -> dict:
        """Chama um RPC em membros da swarm, com refresh automatico no 421."""
        last: Exception | None = None
        tentados: list[str] = []
        for attempt in range(tries):
            swarm = self.get_swarm(session_id, force=attempt > 0 and isinstance(last, SwarmChanged))
            # evita os nos que acabaram de falhar e os ja tentados nesta chamada
            opcoes = [n for n in self._saudaveis(swarm) if n.ed25519 not in tentados] or swarm
            node = random.choice(opcoes)
            tentados.append(node.ed25519)
            try:
                return self.rpc(node, method, params)
            except SwarmChanged as exc:
                last = exc
                self._swarms.pop(session_id, None)
                self._log(t("the swarm of {sid}... changed, refreshing", sid=session_id[:10]))
            except SnodeError as exc:
                last = exc
                self.marcar_falha(node)
                self._log(f"{method}: {exc}")
        raise SnodeError(
            t(
                "{method} failed on {n} swarm nodes: {last}",
                method=method,
                n=len(tentados),
                last=last,
            )
        )

    # --- relogio da rede -----------------------------------------------------

    def sync_clock(self) -> int:
        """Alinha o relogio com a rede (as assinaturas valem +/- 60s)."""
        result = self.rpc_any("info", {})
        network_ms = int(result.get("t") or result.get("timestamp") or 0)
        if network_ms:
            self._clock_offset_ms = network_ms - int(time.time() * 1000)
            if abs(self._clock_offset_ms) > 2000:
                self._log(t("local clock corrected by {ms} ms", ms=self._clock_offset_ms))
        return self.now_ms()

    def now_ms(self) -> int:
        return int(time.time() * 1000) + self._clock_offset_ms

    # --- endpoints de mensagem ----------------------------------------------

    def store(
        self,
        session_id: str,
        data: bytes,
        *,
        ttl_ms: int = TTL_DEFAULT_MS,
        timestamp_ms: int | None = None,
        namespace: int = NAMESPACE_DEFAULT,
    ) -> dict:
        """Deposita uma mensagem na swarm do destinatario.

        O namespace 0 (mensagens 1-para-1) aceita deposito sem autenticacao:
        qualquer um pode escrever na caixa de entrada de qualquer Session ID --
        e so o dono consegue ler.
        """
        if len(data) > MAX_MESSAGE_BODY:
            raise SnodeError(
                t("message too large: {n} > {max} bytes", n=len(data), max=MAX_MESSAGE_BODY)
            )
        params = {
            "pubkey": session_id,
            "timestamp": timestamp_ms if timestamp_ms is not None else self.now_ms(),
            "ttl": str(ttl_ms),
            "data": b64encode(data).decode("ascii"),
        }
        if namespace:
            params["namespace"] = namespace
        result = self.swarm_rpc(session_id, "store", params)

        swarm_result = result.get("swarm") or {}
        stored = [v for v in swarm_result.values() if not v.get("failed")]
        if swarm_result and not stored:
            reasons = {v.get("reason") or v.get("code") for v in swarm_result.values()}
            raise SnodeError(t("no swarm node accepted the message: {reasons}", reasons=reasons))
        return {
            "accepted": len(stored),
            "swarm_size": len(swarm_result),
            "hash": next((v.get("hash") for v in stored if v.get("hash")), None),
            "raw": result,
        }

    def retrieve(
        self,
        identity: Identity,
        *,
        namespace: int = NAMESPACE_DEFAULT,
        last_hash: str | None = None,
        max_count: int | None = None,
    ) -> dict:
        """Busca mensagens da propria caixa (exige assinatura Ed25519)."""
        timestamp = self.now_ms()
        to_sign = b"retrieve"
        if namespace:
            to_sign += str(namespace).encode()
        to_sign += str(timestamp).encode()
        signature = keys.sign_detached(to_sign, identity.ed25519_sk)

        params: dict = {
            "pubkey": identity.session_id,
            "pubkey_ed25519": identity.ed25519_pk.hex(),
            "timestamp": timestamp,
            "signature": b64encode(signature).decode("ascii"),
        }
        if namespace:
            params["namespace"] = namespace
        if last_hash:
            params["last_hash"] = last_hash
        if max_count:
            params["max_count"] = max_count

        result = self.swarm_rpc(identity.session_id, "retrieve", params)
        return {
            "messages": result.get("messages") or [],
            "more": bool(result.get("more")),
            "raw": result,
        }
