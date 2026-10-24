"""
Session from the terminal -- your own account, no official app running.

    session-tui                              opens the live TUI
    session-tui tui --to 05ab...             opens the TUI on a conversation
    session-tui new                          creates the account, shows the phrase
    session-tui import "13 words"            recovers an existing account
    session-tui me                           shows your Session ID
    session-tui send 05ab... "hi"            sends a message and exits
    session-tui file 05ab... photo.png       sends an image (or any file)
    session-tui view photo.png               draws an image in the terminal
    session-tui listen                       prints incoming messages
    session-tui network                      network diagnostics
    session-tui protect | unprotect          password on the account seed
    session-tui killswitch [on|off|...]      erase everything after a time without access
    session-tui lang [en|pt]                 interface language
    session-tui test [--network]             protocol tests

From source, use `python main.py ...` instead of `session-tui ...`. The
Portuguese command names (nova, importar, eu, enviar, ...) work as aliases.
"""

from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

from imgview import MODOS as MODOS_IMAGEM
from imgview import normalizar_modo
from session_native import i18n, killswitch, sistema
from session_native.attachments import AttachmentError
from session_native.client import SessionClient
from session_native.cofre import CofreError, SenhaErrada
from session_native.i18n import t
from session_native.keys import Identity, InvalidSessionID
from session_native.profile import Profile
from session_native.snode import SnodeError, SnodeNetwork

PERFIL_PADRAO = str(sistema.pasta_perfil_padrao())
SAIDA_KILLSWITCH = 3  # codigo de saida quando o kill switch disparou

ACOES_KILLSWITCH = {
    "status": "status",
    "on": "on",
    "ligar": "on",
    "off": "off",
    "desligar": "off",
    "check": "check",
    "verificar": "check",
    "install": "install",
    "instalar": "install",
    "uninstall": "uninstall",
    "remover": "uninstall",
}


def _log(msg: str) -> None:
    print(f"  . {msg}")


def _linha(rotulo: str, valor) -> None:
    print(f"  {rotulo:<22}: {valor}")


def _sim_nao(valor: bool) -> str:
    return t("yes") if valor else t("no")


def _senha(args, perfil: Profile | None = None) -> str | None:
    """Senha da conta: a da linha de comando, ou perguntada na hora.

    Sem terminal interativo (pipe, script, agendador) nao da para perguntar --
    melhor falhar explicando do que ficar esperando uma resposta que nao vem.
    """
    if getattr(args, "senha", None):
        return args.senha
    alvo = perfil or Profile.open(args.perfil)
    if not (alvo.has_account() and alvo.is_protected()):
        return None
    if not (sys.stdin and sys.stdin.isatty()):
        raise SystemExit(
            t(
                "  the account is password-protected and there is no terminal to ask.\n"
                "  use --password PASSWORD (careful: it stays in the shell history)"
            )
        )
    try:
        return getpass.getpass(t("  account password: "))
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(t("\n  no password, nothing to do")) from None


def _mostrar_frase(client: SessionClient) -> None:
    _linha(t("phrase"), client.identity.mnemonic)
    print()
    print(t("  SAVE THE PHRASE: it is the only way to recover the account."))


def _abrir(args, *, create: bool = False, mnemonic: str | None = None) -> SessionClient:
    """Abre o perfil; avisa quando cria uma conta na hora."""
    perfil = Profile.open(args.perfil)
    nova = create and not perfil.has_account()
    client = SessionClient.open(
        args.perfil,
        use_onion=args.onion,
        create=create,
        mnemonic=mnemonic,
        senha=_senha(args, perfil),
        log=_log if args.verboso else None,
    )
    disparo = killswitch.ultimo_disparo(client.profile)
    if disparo:  # disparou com o programa fechado (agendador)
        _relatar_disparo(disparo)
        killswitch.marcar_visto(client.profile)
        print()
    if nova or not client.profile.state.get("anunciada"):
        if nova:
            print(t("  account created in {path}", path=args.perfil))
        _linha("Session ID", client.session_id)
        _mostrar_frase(client)
        print()
        client.profile.state["anunciada"] = True
        client.profile.save_state()
    return client


def _mostrar_conta(client: SessionClient, *, com_frase: bool) -> None:
    print()
    _linha("Session ID", client.session_id)
    if com_frase:
        _mostrar_frase(client)
        print(t("  (also saved in {path})", path=client.profile.account_path))
    print()


# --- kill switch ------------------------------------------------------------


def _relatar_disparo(disparo: killswitch.Disparo) -> None:
    print(t("  KILL SWITCH FIRED on {when}", when=killswitch.formatar_data(disparo.quando)))
    print(t("  erased: {files}", files=", ".join(disparo.apagados) or "-"))
    if disparo.aviso_pulado:
        print(t("  contacts NOT notified: {reason}", reason=disparo.aviso_pulado))
    elif disparo.avisados or disparo.falhas:
        print(
            t(
                "  notice sent to {ok} of {n} contact(s) ({failed} failed)",
                ok=disparo.avisados,
                n=disparo.contatos,
                failed=disparo.falhas,
            )
        )
    if disparo.novo_id:
        print(t("  new account: {sid}", sid=disparo.novo_id))
    else:
        print(t("  no new account was created"))


def _verificar_killswitch(args) -> killswitch.Disparo | None:
    """Roda antes de qualquer comando: se o prazo venceu, dispara agora."""
    perfil = Profile.open(args.perfil)
    if not killswitch.vencido(perfil):
        return None
    cfg = killswitch.carregar(perfil)
    print(t("  kill switch: no access for more than {time} -- erasing everything...", time=cfg.descricao()))
    disparo = killswitch.disparar(perfil, use_onion=args.onion, log=_log)
    _relatar_disparo(disparo)
    print()
    return disparo


def _mostrar_killswitch(perfil: Profile) -> None:
    cfg = killswitch.carregar(perfil)
    print()
    if cfg.ativo:
        print(t("  kill switch ON: erases after {time} without access", time=cfg.descricao()))
    else:
        print(t("  kill switch OFF"))
    _linha(t("last access"), killswitch.formatar_data(killswitch.ultimo_acesso(perfil)))
    prazo = killswitch.prazo(perfil, cfg)
    if prazo:
        falta = killswitch.formatar_duracao(prazo - time.time())
        _linha(t("erases at"), t("{when} (in {time})", when=killswitch.formatar_data(prazo), time=falta))
    _linha(t("notify contacts"), _sim_nao(cfg.avisar))
    _linha(t("create new account"), _sim_nao(cfg.nova_conta))
    _linha(
        t("automatic check"),
        t("installed (every hour)") if sistema.agendamento_instalado(perfil.path) else t("not installed"),
    )
    anterior = killswitch.ultimo_disparo(perfil, so_nao_visto=False)
    if anterior:
        _linha(t("last fired"), killswitch.formatar_data(anterior.quando))
    if cfg.avisar and perfil.is_protected():
        print()
        print(t("  note: a password-protected account cannot notify contacts when the"))
        print(t("  kill switch fires -- the key that signs the notice is locked"))
    print()


def _instalar_agendamento(perfil: Profile) -> bool:
    try:
        como = sistema.instalar_agendamento(perfil.path)
    except RuntimeError as exc:
        print(t("  could not install the automatic check: {error}", error=exc))
        return False
    print(t("  automatic check installed: {how}", how=como))
    return True


# --- comandos ---------------------------------------------------------------


def cmd_tui(args) -> int:
    from tui import run  # importado aqui para nao exigir textual nos outros comandos

    run(args.perfil, use_onion=args.onion, destino=args.para, modo_imagem=args.modo)
    return 0


def cmd_nova(args) -> int:
    profile = Profile.open(args.perfil)
    if profile.has_account() and not args.forcar:
        client = _abrir(args)
        print(t("  there is already an account in this profile (use --force to replace it)"))
        _mostrar_conta(client, com_frase=False)
        return 1
    identity = Identity.generate()
    profile.save_identity(identity)
    profile.state["anunciada"] = True
    profile.save_state()
    killswitch.registrar_acesso(profile, forcar=True)
    print(t("  account created"))
    print()
    _linha("Session ID", identity.session_id)
    _linha(t("phrase"), identity.mnemonic)
    print()
    print(t("  SAVE THE PHRASE: it is the only way to recover the account."))
    print(t("  (also saved in {path})", path=profile.account_path))
    return 0


def cmd_importar(args) -> int:
    profile = Profile.open(args.perfil)
    if profile.has_account() and not args.forcar:
        print(t("  there is already an account in this profile (use --force to replace it)"))
        return 1
    try:
        identity = Identity.from_mnemonic(args.frase)
    except ValueError as exc:
        print(t("  invalid phrase: {error}", error=exc))
        return 1
    profile.save_identity(identity)
    profile.state["anunciada"] = True
    profile.save_state()
    killswitch.registrar_acesso(profile, forcar=True)
    print(t("  account imported"))
    _linha("Session ID", identity.session_id)
    return 0


def cmd_proteger(args) -> int:
    perfil = Profile.open(args.perfil)
    if not perfil.has_account():
        print(t("  no account in {path}", path=args.perfil))
        return 1
    if perfil.is_protected():
        print(t("  this account is already protected (use `unprotect` to remove it)"))
        return 1
    nova = args.senha or getpass.getpass(t("  new password: "))
    if len(nova) < 8:
        print(t("  use at least 8 characters"))
        return 1
    if not args.senha and nova != getpass.getpass(t("  repeat the password: ")):
        print(t("  the passwords do not match"))
        return 1
    try:
        perfil.set_password(nova)
    except CofreError as exc:
        print(t("  failed: {error}", error=exc))
        return 1
    print(t("  account protected: the seed is now encrypted (Argon2id + XChaCha20-Poly1305)"))
    print(t("  the password will be asked every time the profile is opened"))
    print(t("  there is no way to recover the password -- keep the recovery phrase too"))
    if killswitch.carregar(perfil).avisar:
        print(t("  note: with a password, the kill switch can no longer notify your contacts"))
    return 0


def cmd_desproteger(args) -> int:
    perfil = Profile.open(args.perfil)
    if not perfil.is_protected():
        print(t("  this account is not protected"))
        return 1
    atual = args.senha or getpass.getpass(t("  current password: "))
    try:
        perfil.set_password(None, atual)
    except SenhaErrada:
        print(t("  wrong password"))
        return 1
    except CofreError as exc:
        print(t("  failed: {error}", error=exc))
        return 1
    print(t("  protection removed: the seed is in clear text again in account.json"))
    return 0


def cmd_eu(args) -> int:
    client = _abrir(args, create=True)
    _mostrar_conta(client, com_frase=args.frase)
    return 0


def cmd_enviar(args) -> int:
    client = _abrir(args, create=True)
    texto = " ".join(args.texto)
    try:
        result = client.send_text(args.destino, texto)
    except InvalidSessionID as exc:
        print(t("  invalid destination: {error}", error=exc))
        return 1
    except SnodeError as exc:
        print(t("  sending failed: {error}", error=exc))
        return 1
    print(
        t(
            "  sent: {ok}/{n} swarm nodes stored it ({size} B)",
            ok=result.accepted,
            n=result.swarm_size,
            size=result.size_bytes,
        )
    )
    print(f"  hash: {result.hash}")
    if result.hash_matches is False:
        print(t("  warning: the snode's hash does not match the local calculation"))
    return 0 if result.ok else 1


def cmd_imagem(args) -> int:
    client = _abrir(args, create=True)
    legenda = " ".join(args.legenda) if args.legenda else None
    try:
        result = client.send_file(args.destino, args.caminho, caption=legenda)
    except InvalidSessionID as exc:
        print(t("  invalid destination: {error}", error=exc))
        return 1
    except FileNotFoundError as exc:
        print(f"  {exc}")
        return 1
    except (SnodeError, AttachmentError) as exc:
        print(t("  sending failed: {error}", error=exc))
        return 1
    print(t("  attachment: {n} B encrypted on the file server", n=result.attachment_bytes))
    print(f"  url: {result.attachment_url}")
    print(t("  sent: {ok}/{n} swarm nodes stored it", ok=result.accepted, n=result.swarm_size))
    return 0 if result.ok else 1


def cmd_ver(args) -> int:
    import imgview

    # fora da TUI ninguem disputa o stdin, entao os modos graficos podem sondar
    if args.modo in imgview.MODOS_GRAFICOS and not imgview.preparar_graficos():
        print(t("  this terminal did not answer the probe; using half-blocks"))
        args.modo = "half"
    try:
        from rich.console import Console

        Console().print(imgview.renderizar(args.caminho, largura=args.largura, modo=args.modo))
    except imgview.ImagemError as exc:
        print(f"  {exc}")
        return 1
    return 0


def cmd_ouvir(args) -> int:
    client = _abrir(args, create=True)
    print(t("  listening on {sid}", sid=client.session_id))
    print(t("  (every {s}s, ctrl+c to quit)", s=args.intervalo))
    try:
        while True:
            try:
                for msg in client.poll(download_attachments=not args.nao_baixar):
                    if msg.kind == "empty":
                        continue
                    quando = time.strftime("%H:%M:%S", time.localtime(msg.timestamp_ms / 1000))
                    autor = msg.display_name or msg.sender[:12] + "..."
                    corpo = msg.body if msg.body is not None else f"({msg.kind})"
                    marca = " (sync)" if msg.is_sync else ""
                    print(f"  {quando} {autor}{marca}: {corpo}")
                    for anexo in msg.attachments:
                        print(t("           [attachment] {desc}", desc=anexo.descricao))
                        if anexo.local_path:
                            print(t("           saved in {path}", path=anexo.local_path))
                    if args.verboso:
                        print(t("           from {sid}", sid=msg.sender))
            except (SnodeError, OSError) as exc:
                print(t("  . network: {error}", error=exc))
            if args.uma_vez:
                return 0
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print(t("\n  bye"))
        return 0


def cmd_rede(args) -> int:
    network = SnodeNetwork(use_onion=args.onion, log=_log)
    try:
        pool = network.ensure_pool(force=args.atualizar)
        _linha(t("known service nodes"), len(pool))
        _linha(t("network clock"), f"{network.sync_clock()} ms")
        _linha(t("transport"), t("onion (3 hops)") if args.onion else t("direct"))
        profile = Profile.open(args.perfil)
        if profile.has_account():
            sid = profile.account_session_id() or profile.load_identity().session_id
            swarm = network.get_swarm(sid)
            _linha(t("my swarm"), t("{n} nodes", n=len(swarm)))
            for node in swarm:
                print(f"    - {node.short}  ed25519 {node.ed25519[:16]}...")
        if args.destino:
            swarm = network.get_swarm(args.destino)
            _linha(t("destination swarm"), t("{n} nodes", n=len(swarm)))
            for node in swarm:
                print(f"    - {node.short}")
    except (SnodeError, InvalidSessionID) as exc:
        print(t("  failed: {error}", error=exc))
        return 1
    return 0


def cmd_killswitch(args) -> int:
    acao = ACOES_KILLSWITCH[args.acao]
    perfil = Profile.open(args.perfil)
    if acao == "check":
        return 0  # a verificacao em si ja rodou em main(), antes de qualquer comando
    if acao == "status":
        _mostrar_killswitch(perfil)
        return 0
    if not perfil.has_account():
        print(t("  no account in {path}", path=args.perfil))
        return 1

    # so quem abre a conta (com a senha, se houver) mexe no kill switch
    _abrir(args)
    cfg = killswitch.carregar(perfil)
    if acao == "on":
        cfg.ativo = True
        if args.apos is not None:
            cfg.quantidade = args.apos
        if args.unidade is not None:
            unidade = killswitch.normalizar_unidade(args.unidade)
            if not unidade:
                print("  " + t("unknown unit: use hours, days, months or years"))
                return 1
            cfg.unidade = unidade
        if args.avisar is not None:
            cfg.avisar = args.avisar
        if args.nova_conta is not None:
            cfg.nova_conta = args.nova_conta
        try:
            killswitch.salvar(perfil, cfg)
        except ValueError as exc:
            print(f"  {exc}")
            return 1
        if args.agendar:
            _instalar_agendamento(perfil)
    elif acao == "off":
        cfg.ativo = False
        killswitch.salvar(perfil, cfg)
        if sistema.agendamento_instalado(perfil.path) and sistema.remover_agendamento(perfil.path):
            print(t("  automatic check removed"))
    elif acao == "install":
        if not cfg.ativo:
            print(t("  turn the kill switch on first: killswitch on --after 30 --unit days"))
            return 1
        if not _instalar_agendamento(perfil):
            return 1
    elif acao == "uninstall":
        if sistema.remover_agendamento(perfil.path):
            print(t("  automatic check removed"))
        else:
            print(t("  there was no automatic check installed"))
    _mostrar_killswitch(perfil)
    return 0


def cmd_idioma(args) -> int:
    perfil = Profile.open(args.perfil)
    if not args.idioma_novo:
        print(t("  language: {name}", name=i18n.NOMES[i18n.idioma()]))
        print(t("  options: en (English), pt (Português)"))
        return 0
    codigo = i18n.normalizar(args.idioma_novo)
    if not codigo:
        print(t("  unknown language: use en or pt"))
        return 1
    perfil.atualizar_config(idioma=codigo)
    i18n.definir_idioma(codigo)
    print(t("  language saved: {name}", name=i18n.NOMES[codigo]))
    return 0


def cmd_testes(args) -> int:
    import selftest

    ok = selftest.offline()
    if args.rede:
        ok = selftest.online(use_onion=args.onion) and ok
    print("\nRESULT:", "all passed" if ok else "there were failures")
    return 0 if ok else 1


# --- linha de comando -------------------------------------------------------


def _modo(valor: str) -> str:
    modo = normalizar_modo(valor)
    if not modo:
        raise argparse.ArgumentTypeError(
            t("unknown mode: {mode} (options: {modes})", mode=valor, modes=", ".join(MODOS_IMAGEM))
        )
    return modo


def _opcoes_gerais(parser: argparse.ArgumentParser, *, com_padrao: bool) -> None:
    """As opcoes gerais, aceitas antes e DEPOIS do subcomando.

    Na copia que vai em cada subcomando o padrao e SUPPRESS: a ausencia da
    opcao ali nao apaga o valor dado antes do subcomando.
    """

    def padrao(valor):
        return valor if com_padrao else argparse.SUPPRESS

    parser.add_argument(
        "--profile",
        "--perfil",
        dest="perfil",
        default=padrao(PERFIL_PADRAO),
        help=t("account folder (default: {path})", path=PERFIL_PADRAO.replace("%", "%%")),
    )
    parser.add_argument(
        "--onion", action="store_true", default=padrao(False), help=t("3-hop onion routing")
    )
    parser.add_argument(
        "-v",
        "--verbose",
        "--verboso",
        dest="verboso",
        action="store_true",
        default=padrao(False),
        help=t("shows network details"),
    )
    parser.add_argument(
        "--password",
        "--senha",
        dest="senha",
        default=padrao(None),
        help=t("password of the protected account (asked if missing)"),
    )
    parser.add_argument(
        "--lang",
        "--idioma",
        dest="idioma",
        default=padrao(None),
        help=t("interface language for this run: en or pt"),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-tui",
        description=t("native terminal Session client (your own account, no official app)"),
    )
    _opcoes_gerais(parser, com_padrao=True)
    comum = argparse.ArgumentParser(add_help=False)
    _opcoes_gerais(comum, com_padrao=False)

    subs = parser.add_subparsers(dest="comando", metavar=t("command"))

    p_tui = subs.add_parser("tui", parents=[comum], help=t("live terminal interface (default)"))
    p_tui.add_argument("--to", "--para", dest="para", help=t("Session ID of the first conversation"))
    p_tui.add_argument(
        "--mode",
        "--modo",
        dest="modo",
        default="half",
        type=_modo,
        help=t("how to draw images: {modes}", modes=", ".join(MODOS_IMAGEM)),
    )
    p_tui.set_defaults(func=cmd_tui)

    p_nova = subs.add_parser("new", aliases=["nova"], parents=[comum], help=t("creates a new account"))
    p_nova.add_argument(
        "--force", "--forcar", dest="forcar", action="store_true", help=t("replaces the existing account")
    )
    p_nova.set_defaults(func=cmd_nova)

    p_imp = subs.add_parser(
        "import",
        aliases=["importar"],
        parents=[comum],
        help=t("recovers an account from the 13-word phrase"),
    )
    p_imp.add_argument("frase", help=t("the 13 words, in quotes"))
    p_imp.add_argument(
        "--force", "--forcar", dest="forcar", action="store_true", help=t("replaces the existing account")
    )
    p_imp.set_defaults(func=cmd_importar)

    p_prot = subs.add_parser(
        "protect", aliases=["proteger"], parents=[comum], help=t("encrypts the account seed with a password")
    )
    p_prot.set_defaults(func=cmd_proteger)

    p_desp = subs.add_parser(
        "unprotect", aliases=["desproteger"], parents=[comum], help=t("removes the account password")
    )
    p_desp.set_defaults(func=cmd_desproteger)

    p_eu = subs.add_parser("me", aliases=["eu"], parents=[comum], help=t("shows your Session ID"))
    p_eu.add_argument(
        "--phrase", "--frase", dest="frase", action="store_true", help=t("also shows the recovery phrase")
    )
    p_eu.set_defaults(func=cmd_eu)

    p_env = subs.add_parser(
        "send", aliases=["enviar"], parents=[comum], help=t("sends a message and exits")
    )
    p_env.add_argument("destino", help=t("destination Session ID (05...)"))
    p_env.add_argument("texto", nargs="+", help=t("the message text"))
    p_env.set_defaults(func=cmd_enviar)

    p_img = subs.add_parser(
        "file",
        aliases=["imagem", "image", "arquivo"],
        parents=[comum],
        help=t("sends an image or file and exits"),
    )
    p_img.add_argument("destino", help=t("destination Session ID (05...)"))
    p_img.add_argument("caminho", help=t("path of the file"))
    p_img.add_argument("legenda", nargs="*", help=t("optional caption"))
    p_img.set_defaults(func=cmd_imagem)

    p_ver = subs.add_parser(
        "view", aliases=["ver"], parents=[comum], help=t("draws an image in the terminal")
    )
    p_ver.add_argument("caminho", help=t("path of the image"))
    p_ver.add_argument(
        "--width", "--largura", dest="largura", type=int, default=44, help=t("width in cells")
    )
    p_ver.add_argument(
        "--mode",
        "--modo",
        dest="modo",
        default="half",
        type=_modo,
        help=t("how to draw images: {modes}", modes=", ".join(MODOS_IMAGEM)),
    )
    p_ver.set_defaults(func=cmd_ver)

    p_ouv = subs.add_parser(
        "listen", aliases=["ouvir"], parents=[comum], help=t("prints incoming messages")
    )
    p_ouv.add_argument(
        "--interval",
        "--intervalo",
        dest="intervalo",
        type=float,
        default=5.0,
        help=t("seconds between fetches"),
    )
    p_ouv.add_argument(
        "--once", "--uma-vez", dest="uma_vez", action="store_true", help=t("fetches once and exits")
    )
    p_ouv.add_argument(
        "--no-download",
        "--nao-baixar",
        dest="nao_baixar",
        action="store_true",
        help=t("shows attachments but does not download them"),
    )
    p_ouv.set_defaults(func=cmd_ouvir)

    p_rede = subs.add_parser(
        "network", aliases=["rede"], parents=[comum], help=t("network and swarm diagnostics")
    )
    p_rede.add_argument("--to", "--destino", dest="destino", help=t("also shows this Session ID's swarm"))
    p_rede.add_argument(
        "--refresh", "--atualizar", dest="atualizar", action="store_true", help=t("rebuilds the node list")
    )
    p_rede.set_defaults(func=cmd_rede)

    p_ks = subs.add_parser(
        "killswitch",
        aliases=["ks"],
        parents=[comum],
        help=t("erases everything after a time without access"),
        description=t(
            "on: turn on (with --after/--unit/...), off: turn off, status: show, "
            "install/uninstall: automatic hourly check, check: run the check now"
        ),
    )
    p_ks.add_argument("acao", nargs="?", default="status", choices=list(ACOES_KILLSWITCH))
    p_ks.add_argument("--after", "--apos", dest="apos", type=int, help=t("how many units without access"))
    p_ks.add_argument("--unit", "--unidade", dest="unidade", help=t("hours, days, months or years"))
    p_ks.add_argument(
        "--notify",
        "--avisar",
        dest="avisar",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=t("notify your contacts before erasing"),
    )
    p_ks.add_argument(
        "--new-account",
        "--nova-conta",
        dest="nova_conta",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=t("create a new account after erasing"),
    )
    p_ks.add_argument(
        "--schedule",
        "--agendar",
        dest="agendar",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=t("install the automatic hourly check (default: yes)"),
    )
    p_ks.set_defaults(func=cmd_killswitch)

    p_lang = subs.add_parser(
        "lang", aliases=["idioma", "language"], parents=[comum], help=t("interface language: en or pt")
    )
    p_lang.add_argument("idioma_novo", nargs="?", metavar="en|pt")
    p_lang.set_defaults(func=cmd_idioma)

    p_test = subs.add_parser("test", aliases=["testes"], parents=[comum], help=t("protocol tests"))
    p_test.add_argument(
        "--network", "--rede", dest="rede", action="store_true", help=t("includes a real round trip")
    )
    p_test.set_defaults(func=cmd_testes)

    return parser


def _valor_de(argumentos: list[str], nomes: tuple[str, ...]) -> str | None:
    """Valor de uma opcao (`--x v` ou `--x=v`) antes do argparse existir."""
    for i, arg in enumerate(argumentos):
        for nome in nomes:
            if arg == nome and i + 1 < len(argumentos):
                return argumentos[i + 1]
            if arg.startswith(nome + "="):
                return arg.split("=", 1)[1]
    return None


def _idioma_inicial(argumentos: list[str]) -> str:
    """--lang desta execucao, ou o idioma salvo no perfil, ou ingles.

    Precisa vir antes do argparse: a propria ajuda ja sai traduzida.
    """
    pedido = i18n.normalizar(_valor_de(argumentos, ("--lang", "--idioma")))
    if pedido:
        return pedido
    perfil = _valor_de(argumentos, ("--profile", "--perfil")) or PERFIL_PADRAO
    salvo = Profile(path=Path(perfil)).ler_config().get("idioma")
    return i18n.normalizar(salvo) or i18n.PADRAO


def main(argv: list[str] | None = None) -> int:
    sistema.configurar_saida()
    argumentos = list(sys.argv[1:] if argv is None else argv)
    i18n.definir_idioma(_idioma_inicial(argumentos))
    parser = build_parser()
    args = parser.parse_args(argumentos)
    if not getattr(args, "comando", None):
        # sem subcomando: abre a TUI, preservando as opcoes globais passadas
        args = parser.parse_args(argumentos + ["tui"])
    try:
        if args.func not in (cmd_testes, cmd_ver, cmd_idioma):
            disparo = _verificar_killswitch(args)
            if disparo is not None:
                if args.func is cmd_killswitch and ACOES_KILLSWITCH[args.acao] == "check":
                    return 0  # agendador: ninguem viu, a interface mostra depois
                if args.func is not cmd_tui:  # a TUI mostra o relato ela mesma
                    killswitch.marcar_visto(Profile.open(args.perfil))
                    print(t("  the command was not run: the account it would use was erased"))
                    return SAIDA_KILLSWITCH
        return args.func(args)
    except SenhaErrada:
        print(t("  wrong password"))
        return 1
    except CofreError as exc:
        print(f"  {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"  {exc}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
