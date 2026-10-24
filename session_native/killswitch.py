"""Kill switch: apaga a conta depois de um tempo sem acesso.

Configuracao (em `config.json` do perfil, que sobrevive ao apagar tudo):

    ativo       liga/desliga
    quantidade  + unidade (horas, dias, meses, anos) = tempo maximo sem acesso
    avisar      manda aos contatos, pela conta antiga, o ID novo (ou que a
                conta foi encerrada) antes de apagar
    nova_conta  cria uma conta nova logo depois de apagar

"Acesso" e usar a conta: abrir pelo CLI ou pela TUI (com a senha, se houver)
e, com a TUI aberta, a cada poucos minutos. A verificacao roda em toda
abertura do programa e, com o agendador do sistema instalado
(`sistema.instalar_agendamento`), de hora em hora mesmo com o programa fechado.

Limites, para ninguem se enganar:

* conta protegida por senha nao consegue avisar os contatos sozinha -- a chave
  que assina o aviso esta cifrada e o agendador nao sabe a senha. Ela e apagada
  do mesmo jeito; so o aviso fica de fora;
* quem copiou os arquivos antes do prazo continua com a copia;
* apagar em SSD ou pasta sincronizada na nuvem nao garante que os bytes somem.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from .i18n import t
from .keys import Identity
from .profile import Profile

HORA = 3600
SEGUNDOS = {"hours": HORA, "days": 24 * HORA, "months": 30 * 24 * HORA, "years": 365 * 24 * HORA}
UNIDADES = tuple(SEGUNDOS)
MAXIMO_S = 100 * SEGUNDOS["years"]
INTERVALO_REGISTRO_S = 5 * 60  # nao regrava o ultimo acesso a cada poll
LOG_FILE = "killswitch.log"

# o texto do aviso e fixo em ingles: quem recebe pode falar qualquer lingua
MENSAGEM_MIGRACAO = "I am moving my account to:{novo}"
MENSAGEM_ENCERRADA = "This account is no longer in use."

_APELIDOS = {
    "h": "hours", "hour": "hours", "hours": "hours", "hora": "hours", "horas": "hours",
    "d": "days", "day": "days", "days": "days", "dia": "days", "dias": "days",
    "mo": "months", "month": "months", "months": "months",
    "mes": "months", "mês": "months", "meses": "months",
    "y": "years", "year": "years", "years": "years",
    "a": "years", "ano": "years", "anos": "years",
}  # fmt: skip


def normalizar_unidade(valor: str | None) -> str | None:
    """'dias', 'd', 'months', 'anos'... -> 'days' / 'months' / ... (ou None)."""
    return _APELIDOS.get((valor or "").strip().lower())


def rotulo_unidade(unidade: str, quantidade: int) -> str:
    singular = quantidade == 1
    if unidade == "hours":
        return t("hour") if singular else t("hours")
    if unidade == "days":
        return t("day") if singular else t("days")
    if unidade == "months":
        return t("month") if singular else t("months")
    return t("year") if singular else t("years")


def formatar_duracao(segundos: float) -> str:
    """3 dias e 4 horas -> '3d 4h' (neutro, serve nas duas linguas)."""
    segundos = max(0, int(segundos))
    dias, resto = divmod(segundos, 24 * HORA)
    horas, resto = divmod(resto, HORA)
    minutos = resto // 60
    if dias:
        return f"{dias}d {horas}h"
    if horas:
        return f"{horas}h {minutos}min"
    return f"{minutos}min"


def formatar_data(quando: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(quando)) if quando else "-"


@dataclass
class Config:
    ativo: bool = False
    quantidade: int = 30
    unidade: str = "days"
    avisar: bool = False
    nova_conta: bool = True

    @property
    def segundos(self) -> int:
        return self.quantidade * SEGUNDOS[self.unidade]

    def descricao(self) -> str:
        return f"{self.quantidade} {rotulo_unidade(self.unidade, self.quantidade)}"

    def validar(self) -> None:
        if self.unidade not in SEGUNDOS:
            raise ValueError(t("unknown unit: use hours, days, months or years"))
        if self.quantidade < 1:
            raise ValueError(t("the time must be at least 1"))
        if self.segundos > MAXIMO_S:
            raise ValueError(t("the time can be at most 100 years"))


@dataclass
class Disparo:
    """O que aconteceu quando o kill switch disparou."""

    quando: float
    apagados: list[str] = field(default_factory=list)
    contatos: int = 0
    avisados: int = 0
    falhas: int = 0
    aviso_pulado: str | None = None  # por que nao avisou, quando era para avisar
    novo_id: str | None = None
    visto: bool = False  # a interface ja mostrou este relato?


# --- configuracao -----------------------------------------------------------


def carregar(profile: Profile) -> Config:
    bruto = profile.ler_config().get("killswitch") or {}
    cfg = Config()
    if not isinstance(bruto, dict):
        return cfg
    try:
        cfg.ativo = bool(bruto.get("ativo", cfg.ativo))
        cfg.quantidade = max(1, int(bruto.get("quantidade", cfg.quantidade)))
        cfg.unidade = normalizar_unidade(bruto.get("unidade")) or cfg.unidade
        cfg.avisar = bool(bruto.get("avisar", cfg.avisar))
        cfg.nova_conta = bool(bruto.get("nova_conta", cfg.nova_conta))
    except (TypeError, ValueError):
        return Config()
    return cfg


def salvar(profile: Profile, cfg: Config) -> None:
    """Grava a configuracao; o relogio recomeca a contar agora."""
    cfg.validar()
    profile.atualizar_config(killswitch=asdict(cfg))
    registrar_acesso(profile, forcar=True)


# --- ultimo acesso ----------------------------------------------------------


def ultimo_acesso(profile: Profile) -> float | None:
    valor = profile.ler_config().get("ultimo_acesso")
    try:
        return float(valor) if valor else None
    except (TypeError, ValueError):
        return None


def registrar_acesso(profile: Profile, *, forcar: bool = False) -> None:
    agora = time.time()
    anterior = ultimo_acesso(profile)
    if not forcar and anterior and 0 <= agora - anterior < INTERVALO_REGISTRO_S:
        return
    try:
        profile.atualizar_config(ultimo_acesso=agora)
    except OSError:
        pass  # disco cheio ou arquivo preso: tenta de novo no proximo acesso


def prazo(profile: Profile, cfg: Config | None = None) -> float | None:
    """Quando o kill switch dispara, se ninguem acessar ate la."""
    cfg = cfg or carregar(profile)
    if not cfg.ativo:
        return None
    return (ultimo_acesso(profile) or time.time()) + cfg.segundos


def vencido(profile: Profile, *, agora: float | None = None) -> bool:
    if not profile.has_account():
        return False
    cfg = carregar(profile)
    if not cfg.ativo:
        return False
    ultimo = ultimo_acesso(profile)
    if ultimo is None:  # ligado sem registro (arquivo editado a mao): conta daqui
        registrar_acesso(profile, forcar=True)
        return False
    agora = time.time() if agora is None else agora
    # relogio que voltou no tempo nao dispara nada
    return agora - ultimo > cfg.segundos


# --- disparo ----------------------------------------------------------------


def avisar_contatos(
    identidade: Identity,
    contatos: list[str],
    novo_id: str | None,
    *,
    network=None,
    cache_path=None,
    use_onion: bool = False,
    log: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """Manda o aviso de mudanca (ou de encerramento) a cada contato.

    Devolve (entregues, falhas). Sai pela conta antiga, que e a que os
    contatos conhecem.
    """
    from .client import SessionClient
    from .snode import SnodeNetwork

    texto = MENSAGEM_MIGRACAO.format(novo=novo_id) if novo_id else MENSAGEM_ENCERRADA
    network = network or SnodeNetwork(use_onion=use_onion, cache_path=cache_path, log=log)
    cliente = SessionClient(identidade, network, None, log=log)
    entregues = falhas = 0
    for contato in contatos:
        try:
            if cliente.send_text(contato, texto).ok:
                entregues += 1
            else:
                falhas += 1
        except Exception as exc:  # um contato com problema nao segura os outros
            falhas += 1
            if log:
                log(t("notice to {contact} failed: {error}", contact=contato[:10], error=exc))
    return entregues, falhas


def disparar(
    profile: Profile,
    *,
    identidade: Identity | None = None,
    use_onion: bool = False,
    log: Callable[[str], None] | None = None,
) -> Disparo:
    """Avisa (se configurado e possivel), apaga tudo e cria a conta nova."""
    cfg = carregar(profile)
    contatos = profile.conhecidos()
    nova =Identity.generate() if cfg.nova_conta else None
    disparo = Disparo(quando=time.time(), contatos=len(contatos))

    if cfg.avisar and contatos:
        if identidade is None and not profile.is_protected():
            try:
                identidade = profile.load_identity()
            except Exception as exc:
                disparo.aviso_pulado = str(exc)
        if identidade is None:
            disparo.aviso_pulado = disparo.aviso_pulado or t(
                "the account is password-protected, so the key that signs the notice is locked"
            )
        else:
            if log:
                log(t("notifying {n} contact(s)...", n=len(contatos)))
            disparo.avisados, disparo.falhas = avisar_contatos(
                identidade,
                contatos,
                nova.session_id if nova else None,
                cache_path=profile.snodes_path,
                use_onion=use_onion,
                log=log,
            )

    disparo.apagados = profile.apagar_tudo(triturar=True)
    if nova:
        profile.save_identity(nova)
        profile.state["anunciada"] = False  # a interface mostra a frase nova
        profile.save_state()
        disparo.novo_id = nova.session_id

    profile.atualizar_config(ultimo_acesso=time.time(), disparo=asdict(disparo))
    _registrar_log(profile, disparo)
    return disparo


def verificar(
    profile: Profile, *, use_onion: bool = False, log: Callable[[str], None] | None = None
) -> Disparo | None:
    """Dispara se o prazo venceu; devolve o relato (ou None)."""
    if not vencido(profile):
        return None
    return disparar(profile, use_onion=use_onion, log=log)


def ultimo_disparo(profile: Profile, *, so_nao_visto: bool = True) -> Disparo | None:
    bruto = profile.ler_config().get("disparo")
    if not isinstance(bruto, dict):
        return None
    try:
        disparo = Disparo(**bruto)
    except TypeError:
        return None
    if so_nao_visto and disparo.visto:
        return None
    return disparo


def marcar_visto(profile: Profile) -> None:
    disparo = ultimo_disparo(profile, so_nao_visto=False)
    if disparo and not disparo.visto:
        disparo.visto = True
        profile.atualizar_config(disparo=asdict(disparo))


def _registrar_log(profile: Profile, disparo: Disparo) -> None:
    """Uma linha por disparo em killswitch.log -- nunca a conta antiga."""
    linha = (
        f"{formatar_data(disparo.quando)} fired: erased={','.join(disparo.apagados) or '-'} "
        f"notified={disparo.avisados}/{disparo.contatos} failed={disparo.falhas} "
        f"skipped={disparo.aviso_pulado or '-'} new_account={disparo.novo_id or '-'}\n"
    )
    try:
        with (profile.path / LOG_FILE).open("a", encoding="utf-8") as arquivo:
            arquivo.write(linha)
    except OSError:
        pass
