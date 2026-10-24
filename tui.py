"""TUI ao vivo para conversar no Session pelo terminal (Textual).

Cada conversa e uma tela: trocar de contato limpa o painel e redesenha so o
historico daquela pessoa. Mensagem que chega de outra conversa nao polui a tela
-- vira aviso na lista (contador de nao lidas) e um toast.

    +-----------------------------------------------------------+
    | network ok | me: 05ab..cd | name: demo | with: alice | ...  |
    +----------------+------------------------------------------+
    | conversations  | conversation with alice                  |
    | > alice        |  12:30:01 you > hello                    |
    |   bob (2)      |  12:30:04 alice < hi!                    |
    +----------------+------------------------------------------+
    | > message, /help, or drag a file here                     |
    +-----------------------------------------------------------+

Botao direito (ou f2) numa conversa abre o cartao do contato, com o ID
completo, apelido, copiar e remover. Os textos vem de `i18n` (ingles ou
portugues); este modulo e importado depois de o idioma ser escolhido, porque
os atalhos (BINDINGS) sao traduzidos na definicao das classes.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
)

import imgview
from session_native import cofre, i18n, keys, killswitch, sistema
from session_native.client import SessionClient
from session_native.i18n import t
from session_native.keys import Identity
from session_native.logo import COR as COR_LOGO
from session_native.logo import LOGO
from session_native.profile import Profile
from session_native.snode import SnodeError

POLL_SECONDS = 5.0
LIGAR = ("on", "ligar", "sim", "yes")
DESLIGAR = ("off", "desligar", "nao", "não", "no")

CORES_AVATAR = ["#31d2a0", "#5891f5", "#f0a63a", "#e8544b", "#a371f7", "#2fb7c4"]


def curto(session_id: str) -> str:
    return f"{session_id[:6]}...{session_id[-4:]}" if len(session_id) > 14 else session_id


def hora(timestamp_ms: int | None) -> str:
    if not timestamp_ms:
        return time.strftime("%H:%M:%S")
    return time.strftime("%H:%M:%S", time.localtime(timestamp_ms / 1000))


def iniciais(nome: str, session_id: str) -> str:
    limpo = "".join(c for c in nome if c.isalnum())
    if len(limpo) >= 2:
        return limpo[:2].upper()
    return session_id[2:4].upper()


def cor_avatar(session_id: str) -> str:
    return CORES_AVATAR[sum(session_id.encode()) % len(CORES_AVATAR)]


# --- mensagens internas ------------------------------------------------------


class AbrirPerfil(Message):
    """Pedido de abrir o cartao de um contato (botao direito na lista)."""

    def __init__(self, session_id: str) -> None:
        super().__init__()
        self.session_id = session_id


class AbrirMeuPerfil(Message):
    """Pedido de abrir o proprio perfil (clique no avatar do topo)."""


class AvatarMeu(Static):
    """Avatar clicavel do dono da conta, no canto da barra de status."""

    def on_click(self, event) -> None:
        event.stop()
        self.post_message(AbrirMeuPerfil())


class FecharX(Static):
    """O 'x' do canto do cartao: fecha a janelinha."""

    def on_click(self, event) -> None:
        event.stop()
        self.screen.dismiss(None)


def barra_titulo(titulo: str, estilo: str = "bold") -> ComposeResult:
    """Linha de topo do cartao: titulo a esquerda, 'x' a direita."""
    with Horizontal(classes="titulo_cartao"):
        yield Static(Text(titulo, style=estilo), classes="titulo_texto")
        yield FecharX(Text(" x ", style="bold"), classes="fechar_x")


class AjudaModal(ModalScreen[None]):
    """A ajuda inteira numa janela rolavel -- no painel ela some no scroll."""

    BINDINGS = [("escape", "fechar", t("close")), ("f1", "fechar", t("close"))]

    def compose(self) -> ComposeResult:
        with Vertical(id="cartao_ajuda"):
            yield from barra_titulo(t("help -- arrows/PgUp/PgDn scroll, esc closes"))
            with VerticalScroll(id="ajuda_texto"):
                yield Static(Text(i18n.longo("help")))
                yield Static(Text("\n\n" + LOGO, style=COR_LOGO))
                yield Static(Text("\nSession TUI", style=f"bold {COR_LOGO}"))
            with Horizontal(id="botoes"):
                yield Button(t("Close"), id="fechar", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#ajuda_texto", VerticalScroll).focus()

    def on_button_pressed(self, _event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_fechar(self) -> None:
        self.dismiss(None)


class PedirSenha(ModalScreen[str | None]):
    """Pede uma senha (opcionalmente duas vezes, para confirmar)."""

    BINDINGS = [("escape", "cancelar", t("cancel"))]

    def __init__(
        self,
        titulo: str,
        descricao: str,
        *,
        confirmar: bool = False,
        rotulo_ok: str = "OK",
    ) -> None:
        super().__init__()
        self.titulo = titulo
        self.descricao = descricao
        self.confirmar = confirmar
        self.rotulo_ok = rotulo_ok

    def compose(self) -> ComposeResult:
        with Vertical(id="cartao"):
            yield from barra_titulo(self.titulo)
            yield Static(Text(self.descricao), id="texto")
            yield Input(placeholder=t("password"), password=True, id="senha")
            if self.confirmar:
                yield Input(placeholder=t("repeat the password"), password=True, id="senha2")
            yield Static(Text("", style="bold red"), id="aviso")
            with Horizontal(id="botoes"):
                yield Button(self.rotulo_ok, id="ok", variant="primary")
                yield Button(t("Cancel"), id="cancelar")

    def on_mount(self) -> None:
        self.query_one("#senha", Input).focus()

    def _avisar(self, texto: str) -> None:
        self.query_one("#aviso", Static).update(Text(texto, style="bold red"))

    def _confirmar(self) -> None:
        senha = self.query_one("#senha", Input).value
        if not senha:
            self._avisar(t("type a password"))
            return
        if self.confirmar:
            if senha != self.query_one("#senha2", Input).value:
                self._avisar(t("the two passwords do not match"))
                return
            if len(senha) < 8:
                self._avisar(t("use at least 8 characters"))
                return
        self.dismiss(senha)

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        self._confirmar()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self._confirmar()
        else:
            self.dismiss(None)

    def action_cancelar(self) -> None:
        self.dismiss(None)


class ItemConversa(ListItem):
    """Linha da lista de conversas, que sabe de quem e."""

    def __init__(self, session_id: str, rotulo: str) -> None:
        super().__init__(Label(rotulo))
        self.session_id = session_id

    def on_click(self, event) -> None:
        if getattr(event, "button", 1) == 3:  # botao direito: cartao
            event.stop()
            self.post_message(AbrirPerfil(self.session_id))


# --- telas modais ------------------------------------------------------------


class CartaoContato(ModalScreen[tuple[str, str] | None]):
    """Cartao do contato, no espirito do app oficial.

    Devolve (acao, valor): 'apelido', 'mensagem', 'remover' ou None.
    """

    BINDINGS = [("escape", "fechar", t("close"))]

    def __init__(self, session_id: str, apelido: str | None, nome_remoto: str | None) -> None:
        super().__init__()
        self.session_id = session_id
        self.apelido = apelido or ""
        self.nome_remoto = nome_remoto or ""

    def compose(self) -> ComposeResult:
        nome = self.apelido or self.nome_remoto or curto(self.session_id)
        with Vertical(id="cartao"):
            yield from barra_titulo(t("contact"))
            yield Static(
                Text(
                    f" {iniciais(nome, self.session_id)} ",
                    style=f"bold on {cor_avatar(self.session_id)}",
                ),
                id="avatar",
            )
            yield Static(Text(nome, style="bold"), id="nome_contato")
            yield Static(Text(t("account ID"), style="dim"), id="rotulo_id")
            yield Static(Text(self.session_id, style="white"), id="id_contato")
            yield Input(value=self.apelido, placeholder=t("nickname (only for you)"), id="apelido")
            with Horizontal(id="botoes"):
                yield Button(t("Message"), id="mensagem", variant="success")
                yield Button(t("Copy"), id="copiar")
                yield Button(t("Save"), id="salvar", variant="primary")
                yield Button(t("Remove"), id="remover", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copiar":
            self.app.copiar_texto(self.session_id)
            self.notify(t("Session ID copied"))
            return
        if event.button.id == "salvar":
            self.dismiss(("apelido", self.query_one("#apelido", Input).value.strip()))
        elif event.button.id == "mensagem":
            self.dismiss(("mensagem", self.session_id))
        elif event.button.id == "remover":
            self.dismiss(("remover", self.session_id))
        else:
            self.dismiss(None)

    def action_fechar(self) -> None:
        self.dismiss(None)


class MeuPerfil(ModalScreen[tuple[str, str] | None]):
    """Cartao da propria conta: nome, Session ID e frase de recuperacao.

    A frase fica escondida ate alguem pedir -- ela e a conta inteira.
    """

    BINDINGS = [("escape", "fechar", t("close"))]

    def __init__(
        self, session_id: str, nome: str | None, frase: str, *, protegida: bool = False
    ) -> None:
        super().__init__()
        self.session_id = session_id
        self.nome = nome or ""
        self.frase = frase
        self.protegida = protegida
        self.mostrando_frase = False

    def compose(self) -> ComposeResult:
        with Vertical(id="cartao"):
            yield from barra_titulo(t("my account"))
            yield Static(
                Text(
                    f" {iniciais(self.nome, self.session_id)} ",
                    style=f"bold on {cor_avatar(self.session_id)}",
                ),
                id="avatar",
            )
            yield Static(Text(self.nome or t("(no name)"), style="bold"), id="nome_contato")
            yield Static(
                Text(
                    t("password-protected") if self.protegida else t("NO password on disk"),
                    style="green" if self.protegida else "bold red",
                ),
                id="rotulo_id",
            )
            yield Static(Text(self.session_id, style="white"), id="id_contato")
            yield Input(
                value=self.nome,
                placeholder=t("display name (sent along with your messages)"),
                id="nome",
            )
            yield Static(Text("", style="bold yellow"), id="frase")
            with Horizontal(id="botoes"):
                yield Button(t("Save"), id="salvar", variant="primary")
                yield Button(t("Copy"), id="copiar")
                yield Button(t("Show phrase"), id="frase_btn", variant="warning")
                yield Button(
                    t("Remove password") if self.protegida else t("Protect"),
                    id="senha",
                    variant="success",
                )
                yield Button(t("Kill switch"), id="killswitch", variant="warning")
                yield Button(i18n.NOMES["pt" if i18n.idioma() == "en" else "en"], id="idioma")
                yield Button(t("Erase everything"), id="apagar", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copiar":
            self.app.copiar_texto(self.session_id)
            self.notify(t("Session ID copied"))
        elif event.button.id == "frase_btn":
            self.mostrando_frase = not self.mostrando_frase
            alvo = self.query_one("#frase", Static)
            if self.mostrando_frase:
                alvo.update(
                    Text(
                        t("whoever has these words controls the account:") + "\n" + self.frase,
                        style="bold yellow",
                    )
                )
                event.button.label = t("Hide phrase")
            else:
                alvo.update(Text(""))
                event.button.label = t("Show phrase")
        elif event.button.id == "salvar":
            self.dismiss(("nome", self.query_one("#nome", Input).value.strip()))
        elif event.button.id == "senha":
            self.dismiss(("senha", "tirar" if self.protegida else "por"))
        elif event.button.id == "killswitch":
            self.dismiss(("killswitch", ""))
        elif event.button.id == "idioma":
            self.dismiss(("idioma", ""))
        elif event.button.id == "apagar":
            self.dismiss(("apagar", ""))
        else:
            self.dismiss(None)

    def action_fechar(self) -> None:
        self.dismiss(None)


class ConfigKillSwitch(ModalScreen[dict | None]):
    """Configura o kill switch: tempo sem acesso, avisar contatos, conta nova.

    Devolve {"cfg": killswitch.Config, "agendar": bool} ou None.
    """

    BINDINGS = [("escape", "cancelar", t("cancel"))]

    def __init__(
        self,
        cfg: killswitch.Config,
        *,
        ultimo: float | None,
        agendado: bool,
        protegida: bool,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.ultimo = ultimo
        self.agendado = agendado
        self.protegida = protegida

    def compose(self) -> ComposeResult:
        unidades = [(t(u), u) for u in ("hours", "days", "months", "years")]
        with Vertical(id="cartao"):
            yield from barra_titulo(t("kill switch"), "bold red")
            yield Static(Text(i18n.longo("killswitch"), style="dim"), id="texto")
            yield Checkbox(t("enabled"), value=self.cfg.ativo, id="ks_ativo")
            with Horizontal(id="ks_tempo"):
                yield Static(Text(t("erase after")), classes="ks_rotulo")
                yield Input(str(self.cfg.quantidade), type="integer", id="ks_quantidade")
                yield Select(unidades, value=self.cfg.unidade, allow_blank=False, id="ks_unidade")
                yield Static(Text(t("without access")), classes="ks_rotulo")
            yield Checkbox(
                t("notify my contacts before erasing"), value=self.cfg.avisar, id="ks_avisar"
            )
            yield Checkbox(
                t("create a new account after erasing"), value=self.cfg.nova_conta, id="ks_nova"
            )
            yield Checkbox(
                t("automatic check every hour, even with the app closed"),
                value=self.agendado or not self.cfg.ativo,
                id="ks_agendar",
            )
            yield Static(Text(self._situacao(), style="dim"), id="ks_situacao")
            yield Static(Text("", style="bold yellow"), id="aviso")
            with Horizontal(id="botoes"):
                yield Button(t("Save"), id="ok", variant="primary")
                yield Button(t("Cancel"), id="cancelar")

    def _situacao(self) -> str:
        linhas = [t("last access: {when}", when=killswitch.formatar_data(self.ultimo))]
        if self.cfg.ativo and self.ultimo:
            prazo = self.ultimo + self.cfg.segundos
            linhas.append(
                t(
                    "erases at: {when} (in {time})",
                    when=killswitch.formatar_data(prazo),
                    time=killswitch.formatar_duracao(prazo - time.time()),
                )
            )
        return "\n".join(linhas)

    def _atualizar_aviso(self) -> None:
        avisar = self.query_one("#ks_avisar", Checkbox).value
        texto = ""
        if avisar and self.protegida:
            texto = t(
                "this account is password-protected: when the kill switch fires, "
                "the key that signs the notice is locked, so contacts will NOT be notified"
            )
        self.query_one("#aviso", Static).update(Text(texto, style="bold yellow"))

    def on_mount(self) -> None:
        self._atualizar_aviso()

    def on_checkbox_changed(self, _event: Checkbox.Changed) -> None:
        self._atualizar_aviso()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "ok":
            self.dismiss(None)
            return
        bruto = self.query_one("#ks_quantidade", Input).value.strip()
        unidade = self.query_one("#ks_unidade", Select).value
        cfg = killswitch.Config(
            ativo=self.query_one("#ks_ativo", Checkbox).value,
            quantidade=int(bruto) if bruto.lstrip("-").isdigit() else 0,
            unidade=unidade if isinstance(unidade, str) else self.cfg.unidade,
            avisar=self.query_one("#ks_avisar", Checkbox).value,
            nova_conta=self.query_one("#ks_nova", Checkbox).value,
        )
        try:
            cfg.validar()
        except ValueError as exc:
            self.query_one("#aviso", Static).update(Text(str(exc), style="bold red"))
            return
        self.dismiss({"cfg": cfg, "agendar": self.query_one("#ks_agendar", Checkbox).value})

    def action_cancelar(self) -> None:
        self.dismiss(None)


class ConfirmarApagar(ModalScreen[dict | None]):
    """Dupla confirmacao do /removeall: ler o aviso e digitar a palavra."""

    BINDINGS = [("escape", "cancelar", t("cancel"))]

    def __init__(self, quantos_contatos: int) -> None:
        super().__init__()
        self.quantos = quantos_contatos
        self.etapa = 1
        self.palavra = t("ERASE")

    def compose(self) -> ComposeResult:
        with Vertical(id="cartao"):
            yield from barra_titulo(t("ERASE EVERYTHING AND START OVER"), "bold red")
            yield Static(
                Text(
                    t(
                        "This erases, with no way back:\n"
                        "  - the current account (private key and recovery phrase)\n"
                        "  - the whole conversation history\n"
                        "  - downloaded and sent attachments\n"
                        "  - the list of {n} conversation(s)\n\n"
                        "Then a new account is created, with another Session ID.\n"
                        "Whoever writes to the old ID no longer reaches you.",
                        n=self.quantos,
                    )
                ),
                id="texto",
            )
            yield Checkbox(
                t("notify my {n} contacts of the new ID before erasing", n=self.quantos),
                value=self.quantos > 0,
                id="avisar",
            )
            yield Static(Text("", style="dim"), id="passo")
            yield Input(placeholder=t("type {word} to confirm", word=self.palavra), id="palavra")
            with Horizontal(id="botoes"):
                yield Button(t("Continue"), id="ok", variant="error")
                yield Button(t("Cancel"), id="cancelar", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#palavra", Input).display = False
        self.query_one("#cancelar", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancelar":
            self.dismiss(None)
            return
        if self.etapa == 1:
            self.etapa = 2
            self.query_one("#passo", Static).update(
                Text(
                    t("Confirmation 2 of 2: type {word} to erase for good.", word=self.palavra),
                    style="bold yellow",
                )
            )
            campo = self.query_one("#palavra", Input)
            campo.display = True
            campo.focus()
            self.query_one("#ok", Button).label = t("Erase everything")
            return
        if self.query_one("#palavra", Input).value.strip().upper() != self.palavra:
            self.query_one("#passo", Static).update(
                Text(t("type exactly {word}", word=self.palavra), style="bold red")
            )
            return
        self.dismiss({"avisar": self.query_one("#avisar", Checkbox).value})

    def action_cancelar(self) -> None:
        self.dismiss(None)


# --- aplicacao ---------------------------------------------------------------


class SessionTUI(App):
    """Cliente Session de terminal, ao vivo."""

    CSS = """
    Screen { layout: vertical; }
    #topo { height: 1; }
    #meuavatar {
        width: 6; height: 1; content-align: center middle;
        background: $primary-darken-3; color: $text;
    }
    #meuavatar:hover { background: $accent; }
    #status { height: 1; width: 1fr; background: $primary-darken-2; color: $text; padding: 0 1; }
    #corpo { height: 1fr; }
    #conversas { width: 28; border-right: solid $primary-darken-3; }
    #chat { width: 1fr; padding: 0 1; }

    #cartao {
        width: 80; max-width: 96%; height: auto; max-height: 96%; padding: 1 2; margin: 1 2;
        background: $surface; border: thick $primary; overflow-y: auto;
    }
    .titulo_cartao { height: 1; width: 100%; }
    .titulo_texto { width: 1fr; }
    .fechar_x { width: 3; content-align: center middle; background: $panel; }
    .fechar_x:hover { background: $error; color: $text; }
    #avatar { content-align: center middle; width: 100%; padding: 1 0; }
    #nome_contato, #rotulo_id, #id_contato { content-align: center middle; width: 100%; }
    #id_contato { padding: 0 0 1 0; }
    #texto { padding: 1 0; }

    /* checkbox de uma linha so: o cartao cabe em terminais baixos */
    #cartao Checkbox { border: none; height: 1; padding: 0; margin: 0 0 1 0; background: $surface; }
    #cartao Checkbox:focus > .toggle--label { text-style: bold underline; }

    /* kill switch: "apagar depois de [30] [dias] sem acesso" numa linha */
    #ks_tempo { height: 3; width: 100%; margin-bottom: 1; }
    .ks_rotulo { width: auto; padding: 1 1 0 0; }
    #ks_quantidade { width: 10; }
    #ks_unidade { width: 18; margin-right: 1; }
    #ks_situacao { padding: 0; }

    /* grade: os botoes quebram em linhas em vez de vazar o cartao */
    #botoes {
        height: auto; width: 100%; padding-top: 1;
        layout: grid; grid-size: 3; grid-rows: 3; grid-gutter: 0 1;
    }
    #botoes Button { width: 100%; margin: 0; }

    #cartao_ajuda {
        width: 90; max-width: 98%; height: 85%; padding: 1 2; margin: 1 2;
        background: $surface; border: thick $primary;
    }
    #ajuda_texto { height: 1fr; width: 100%; padding: 1 0; }
    """

    BINDINGS = [
        ("ctrl+r", "poll", t("fetch now")),
        ("ctrl+l", "limpar", t("clear screen")),
        Binding("ctrl+v", "colar", t("paste image"), priority=True),
        Binding("ctrl+g", "colar", t("paste image"), show=False, priority=True),
        Binding("ctrl+b", "baixar", t("download attachment"), priority=True),
        ("f2", "perfil", t("contact card")),
        ("f3", "meu_perfil", t("my profile")),
        ("f1", "ajuda", t("help")),
        ("ctrl+c", "quit", t("quit")),
    ]

    def __init__(
        self,
        profile_path: str | Path = "session_profile",
        *,
        use_onion: bool = False,
        destino: str | None = None,
        modo_imagem: str = "half",
    ) -> None:
        super().__init__()
        self.profile_path = profile_path
        self.use_onion = use_onion
        self.destino: str | None = destino.strip().lower() if destino else None
        self.client: SessionClient | None = None
        self.pronto = False
        self.contatos: list[str] = []
        self.nao_lidas: dict[str, int] = {}
        self.modo_imagem = imgview.normalizar_modo(modo_imagem) or "half"
        self.largura_imagem = imgview.LARGURA_PADRAO
        self.verboso = False  # /log liga o relato da rede na conversa
        self.auto_baixar = False  # /auto on baixa anexo sem perguntar
        self.ultimo_anexo: Path | None = None  # para o /abrir
        self.senha: str | None = None  # senha da conta, se estiver protegida
        self._acao: tuple[str, float] | None = None  # confirmacao recente no status
        self._oculto: deque[str] = deque(maxlen=500)  # relato da rede guardado
        self._ks_prazo: float | None = None  # quando o kill switch dispara
        self.pendentes: list = []  # mensagens com anexo esperando o /baixar
        self._lock = threading.Lock()  # uma chamada de rede por vez

    # --- montagem -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="topo"):
            yield AvatarMeu(Text(" .. ", style="bold"), id="meuavatar")
            yield Static(t("starting..."), id="status")
        with Horizontal(id="corpo"):
            yield ListView(id="conversas")
            yield RichLog(id="chat", wrap=True, markup=False, highlight=False)
        yield Input(placeholder=t("message, /help, or drag a file here"), id="entrada")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Session TUI"
        self._write(Text(LOGO, style=COR_LOGO))
        self._write(Text(""))
        self.query_one("#entrada", Input).focus()
        self.iniciar_conta()
        self.set_interval(POLL_SECONDS, self.tick)

    def iniciar_conta(self, aviso: str | None = None) -> None:
        """Abre a conta -- pedindo a senha antes, se o arquivo estiver cifrado."""
        perfil = Profile.open(self.profile_path)
        if not (perfil.has_account() and perfil.is_protected()):
            self.abrir_conta(None)
            return

        sid = perfil.account_session_id() or t("protected account")

        def recebeu(senha: str | None) -> None:
            if not senha:
                self.erro(t("without the password this account cannot be opened (/quit to close)"))
                return
            self.senha = senha
            self.abrir_conta(senha)

        self.push_screen(
            PedirSenha(
                t("protected account"),
                (aviso or "")
                + t(
                    "\nthis account is encrypted on disk:\n  {sid}\n\ntype the password to open it.",
                    sid=sid,
                ),
                rotulo_ok=t("Open"),
            ),
            recebeu,
        )

    # --- escrita na tela ----------------------------------------------------

    def _write(self, text) -> None:
        self.query_one("#chat", RichLog).write(text)

    def sistema(self, msg: str, estilo: str = "dim") -> None:
        self._write(Text(f"  {msg}", style=estilo))

    def log_rede(self, msg: str) -> None:
        """Relato da rede: guardado, so aparece com /log ligado.

        Um no fora do ar gera dezenas dessas linhas; elas atrapalham a conversa
        e nao mudam nada do que o usuario pode fazer.
        """
        if self.verboso:
            self.sistema(msg)
            return
        self._oculto.append(f"{time.strftime('%H:%M:%S')} {msg}")
        self.atualizar_status()

    def erro(self, msg: str) -> None:
        self._write(Text(f"  ! {msg}", style="bold red"))

    def aviso(self, msg: str) -> None:
        self._write(Text(f"  {msg}", style="bold yellow"))

    def linha_mensagem(self, *, entrada: bool, autor: str, corpo: str, ts: int | None) -> None:
        line = Text()
        line.append(f"{hora(ts)} ", style="dim")
        if entrada:
            line.append(f"{autor} ", style="bold cyan")
            line.append("< ", style="cyan")
        else:
            line.append(f"{autor} ", style="bold green")
            line.append("> ", style="green")
        line.append(corpo)
        self._write(line)

    def mostrar_imagem(self, caminho: str | Path, *, aviso: bool = True) -> bool:
        """Desenha a imagem no painel. Erro aqui nunca derruba a interface."""
        try:
            desenho = imgview.renderizar(
                caminho, largura=self.largura_imagem, modo=self.modo_imagem
            )
            self._write(desenho)
            return True
        except imgview.ImagemError as exc:
            if aviso:
                self.erro(t("could not show the image: {error}", error=exc))
        except Exception as exc:  # falha inesperada no desenho
            self.erro(
                t("failed to draw the image ({kind}: {error})", kind=type(exc).__name__, error=exc)
            )
        return False

    def copiar_texto(self, texto: str) -> None:
        """Copia pelo terminal (OSC 52) e pela ferramenta do sistema.

        Nem todo terminal entende OSC 52, entao o sistema e o plano B.
        """
        try:
            self.copy_to_clipboard(texto)
        except Exception:
            pass
        sistema.copiar_texto(texto)

    # --- status e lista -----------------------------------------------------

    def nome_de(self, session_id: str) -> str:
        if self.client and self.client.profile:
            apelido = self.client.profile.nickname(session_id)
            if apelido:
                return apelido
        return curto(session_id)

    def acao_concluida(self, texto: str) -> None:
        """Confirmacao curta na barra de status (nao suja a conversa).

        Fica visivel por alguns segundos mesmo que outra atualizacao de status
        aconteca no meio.
        """
        self._acao = (texto, time.time())
        self.atualizar_status()

    def atualizar_avatar(self) -> None:
        """Avatar do dono da conta, clicavel, no canto da barra de status."""
        if not self.client:
            return
        nome = self.client.display_name or ""
        widget = self.query_one("#meuavatar", AvatarMeu)
        widget.update(
            Text(
                f" {iniciais(nome, self.client.session_id)} ",
                style=f"bold on {cor_avatar(self.client.session_id)}",
            )
        )
        widget.tooltip = t("your profile (f3) -- {name}", name=nome or curto(self.client.session_id))

    def atualizar_status(self, extra: str | None = None) -> None:
        if not self.client:
            return
        if self._acao and time.time() - self._acao[1] > 12:
            self._acao = None
        modo = t("onion (3 hops)") if self.client.network.use_onion else t("direct")
        estado = extra or (self._acao[0] if self._acao else None)
        com = self.nome_de(self.destino) if self.destino else t("nobody")
        partes = [
            estado or (t("network ok") if self.pronto else t("connecting...")),
            t("me: {sid}", sid=curto(self.client.session_id)),
            t("name: {name}", name=self.client.display_name or "-"),
            t("with: {who}", who=com),
            modo,
        ]
        if self._ks_prazo:
            partes.append(f"kill switch {killswitch.formatar_duracao(self._ks_prazo - time.time())}")
        if self.pendentes:
            partes.append(t("attachments: {n} (ctrl+b)", n=len(self.pendentes)))
        if self._oculto and not self.verboso:
            partes.append(t("log: {n} (/log)", n=len(self._oculto)))
        self.query_one("#status", Static).update(" | ".join(partes))

    def atualizar_conversas(self) -> None:
        lista = self.query_one("#conversas", ListView)
        lista.clear()
        for sid in self.contatos:
            marca = "> " if sid == self.destino else "  "
            nao_lidas = self.nao_lidas.get(sid, 0)
            sufixo = f" ({nao_lidas})" if nao_lidas else ""
            lista.append(ItemConversa(sid, f"{marca}{self.nome_de(sid)}{sufixo}"))

    def registrar_contato(self, session_id: str) -> None:
        if session_id not in self.contatos:
            self.contatos.append(session_id)
            if self.client and self.client.profile:
                self.client.profile.add_contact(session_id)
            self.atualizar_conversas()

    # --- conversa aberta ----------------------------------------------------

    def abrir_conversa(self, session_id: str | None, *, recarregar: bool = True) -> None:
        """Troca de cena: limpa o painel e redesenha so esta conversa."""
        self.destino = session_id
        if session_id:
            self.nao_lidas.pop(session_id, None)
        if recarregar:
            self.query_one("#chat", RichLog).clear()
            if session_id:
                self.cabecalho_conversa(session_id)
                self.mostrar_historico(limite=40)
            else:
                self.sistema(t("no conversation open -- /to <session_id> starts one"))
        self.atualizar_conversas()
        self.atualizar_status()

    def cabecalho_conversa(self, session_id: str) -> None:
        nome = self.nome_de(session_id)
        linha = Text()
        linha.append(t("conversation with "), style="dim")
        linha.append(nome, style=f"bold {cor_avatar(session_id)}")
        self._write(linha)
        self._write(Text(f"  {session_id}", style="dim"))
        self._write(Text("  " + t("f2 or right click on the list = contact card"), style="dim"))
        self._write(Text(""))

    def mostrar_historico(self, limite: int = 40) -> None:
        if not (self.client and self.client.profile and self.destino):
            return
        entradas = self.client.profile.read_history(peer=self.destino, limit=limite)
        if not entradas:
            self.sistema(t("(no messages yet)"))
            return
        # so as duas imagens mais recentes sao desenhadas, para nao encher a tela
        com_imagem = [e for e in entradas if e.attachment and e.kind == "imagem"]
        desenhar = {id(e) for e in com_imagem[-2:]}

        for entry in entradas:
            if entry.direction == "in":
                autor = self.nome_de(entry.peer) if entry.peer else "?"
            else:
                autor = t("you")
            if entry.attachment:
                corpo = t("[attachment] {name}", name=Path(entry.attachment).name)
                if entry.body:
                    corpo += f" -- {entry.body}"
            else:
                corpo = entry.body or f"({entry.kind})"
            self.linha_mensagem(
                entrada=entry.direction == "in",
                autor=autor,
                corpo=corpo,
                ts=entry.timestamp_ms,
            )
            if id(entry) in desenhar and Path(entry.attachment).is_file():
                self.mostrar_imagem(entry.attachment, aviso=False)

    # --- conta e rede (em threads, para nao travar a interface) -------------

    @work(thread=True, exclusive=True, group="conta")
    def abrir_conta(self, senha: str | None = None) -> None:
        try:
            client = SessionClient.open(
                self.profile_path,
                use_onion=self.use_onion,
                create=True,
                senha=senha,
                log=lambda msg: self.call_from_thread(self.log_rede, msg),
            )
        except cofre.SenhaErrada:
            self.senha = None
            self.call_from_thread(self.iniciar_conta, t("wrong password."))
            return
        except Exception as exc:
            self.call_from_thread(self.erro, t("could not open the profile: {error}", error=exc))
            return
        self.call_from_thread(self._conta_aberta, client)

    def relatar_disparo(self, disparo: killswitch.Disparo) -> None:
        """O kill switch disparou desde a ultima vez: conta o que aconteceu."""
        self.aviso(t("KILL SWITCH FIRED on {when}", when=killswitch.formatar_data(disparo.quando)))
        self.sistema(t("erased: {files}", files=", ".join(disparo.apagados) or "-"))
        if disparo.aviso_pulado:
            self.sistema(t("contacts NOT notified: {reason}", reason=disparo.aviso_pulado))
        elif disparo.avisados or disparo.falhas:
            self.sistema(
                t(
                    "notice sent to {ok} of {n} contact(s) ({failed} failed)",
                    ok=disparo.avisados,
                    n=disparo.contatos,
                    failed=disparo.falhas,
                )
            )
        self._write(Text(""))

    def _conta_aberta(self, client: SessionClient) -> None:
        self.client = client
        profile = client.profile
        nova = not bool(profile.state.get("anunciada"))

        disparo = killswitch.ultimo_disparo(profile)
        if disparo:
            self.relatar_disparo(disparo)
            killswitch.marcar_visto(profile)

        self._write(Text(t("your Session account"), style="bold"))
        self._write(Text(f"  {client.session_id}", style="bold white"))
        if nova:
            self.aviso(t("SAVE THE RECOVERY PHRASE -- it is the only way to recover the account:"))
            self._write(Text(f"  {client.identity.mnemonic}", style="bold yellow"))
            self.sistema(t("(also stored in {path})", path=profile.account_path))
            profile.state["anunciada"] = True
            profile.save_state()
        else:
            self.sistema(t("/phrase shows your recovery phrase, /help lists the commands"))
        self._write(Text(""))

        self.contatos = profile.contacts
        if self.destino:
            try:
                keys.parse_session_id(self.destino)
                self.registrar_contato(self.destino)
            except keys.InvalidSessionID as exc:
                self.erro(t("initial destination ignored: {error}", error=exc))
                self.destino = None
        if not self.destino and self.contatos:
            self.destino = self.contatos[0]
        if self.destino:
            self.cabecalho_conversa(self.destino)
            self.mostrar_historico()
        self._ks_prazo = killswitch.prazo(profile)
        self.atualizar_conversas()
        self.atualizar_avatar()
        self.atualizar_status()
        self.conectar()

    @work(thread=True, exclusive=True, group="conectar")
    def conectar(self) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                pool = self.client.network.ensure_pool()
                self.client.network.sync_clock()
                swarm = self.client.network.get_swarm(self.client.session_id)
        except Exception as exc:
            self.call_from_thread(self.erro, t("network unavailable: {error}", error=exc))
            self.call_from_thread(self.atualizar_status, t("network error"))
            return
        self.pronto = True
        self.call_from_thread(
            self.log_rede,
            t("{n} service nodes, swarm with {m} nodes", n=len(pool), m=len(swarm)),
        )
        self.call_from_thread(self.atualizar_status)

    def tick(self) -> None:
        if self.client and self.client.profile:
            # com a TUI aberta a conta esta em uso: o kill switch nao conta
            killswitch.registrar_acesso(self.client.profile)
            self._ks_prazo = killswitch.prazo(self.client.profile)
            self.atualizar_status()
        if self.pronto and self.client:
            self.buscar_mensagens()

    @work(thread=True, exclusive=True, group="poll")
    def buscar_mensagens(self, anunciar: bool = False) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                mensagens = self.client.poll(download_attachments=self.auto_baixar)
        except SnodeError as exc:
            # falha de busca e comum (no fora do ar); vai para o relato da rede
            self.call_from_thread(self.log_rede, t("fetch failed: {error}", error=exc))
            if anunciar:
                self.call_from_thread(self.erro, t("could not fetch: {error}", error=exc))
            return
        except Exception as exc:
            self.call_from_thread(self.erro, t("unexpected error while fetching: {error}", error=exc))
            return
        if anunciar and not mensagens:
            self.call_from_thread(self.sistema, t("no new messages"))
        for msg in mensagens:
            self.call_from_thread(self._mostrar_recebida, msg)

    def _mostrar_recebida(self, msg) -> None:
        if msg.kind == "typing":
            if self.verboso:
                self.sistema(f"{self.nome_de(msg.sender)} {msg.body}")
            return
        if msg.kind in ("empty", "outro", "unsend") and not msg.attachments:
            self.log_rede(
                t("control message from {sid} ({kind})", sid=curto(msg.sender), kind=msg.kind)
            )
            return

        novo = msg.sender not in self.contatos
        self.registrar_contato(msg.sender)
        if msg.display_name and self.client and self.client.profile:
            if not self.client.profile.nickname(msg.sender):
                self.client.profile.set_nickname(msg.sender, msg.display_name)

        autor = self.nome_de(msg.sender)
        if msg.attachments:
            corpo = t("[attachment] {name}", name=", ".join(a.descricao for a in msg.attachments))
            if msg.body:
                corpo += f" -- {msg.body}"
        else:
            corpo = msg.body if msg.body is not None else f"({msg.kind})"

        if msg.sender != self.destino:
            # outra conversa: nao suja a tela aberta, so avisa
            self.nao_lidas[msg.sender] = self.nao_lidas.get(msg.sender, 0) + 1
            self.atualizar_conversas()
            self.atualizar_status()
            resumo = corpo if len(corpo) <= 60 else corpo[:57] + "..."
            self.notify(
                resumo,
                title=autor + (t(" (new conversation)") if novo else ""),
                timeout=8,
            )
            self.bell()
            if msg.attachments and not any(a.local_path for a in msg.attachments):
                self.pendentes.append(msg)
                self.atualizar_status()
            return

        self.linha_mensagem(entrada=True, autor=autor, corpo=corpo, ts=msg.timestamp_ms)
        if msg.attachments:
            if any(a.local_path for a in msg.attachments):
                self.mostrar_anexos(msg)  # ja veio baixado (/auto on)
            else:
                self.pendentes.append(msg)
                quantos = len(self.pendentes)
                ordem = "" if quantos == 1 else f" {quantos}"
                self.aviso(
                    t("download it? ctrl+b or /download{n}   (/auto on stops asking)", n=ordem)
                )
                self.atualizar_status()
        self.bell()

    # --- envio --------------------------------------------------------------

    @work(thread=True, group="envio")
    def enviar(self, destino: str, texto: str) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                result = self.client.send_text(destino, texto)
        except Exception as exc:
            self.call_from_thread(self.erro, t("not sent: {error}", error=exc))
            return
        # confirmacao vai para a barra de status, nao para a conversa
        self.call_from_thread(
            self.acao_concluida,
            t("ok: sent {ok}/{n}", ok=result.accepted, n=result.swarm_size),
        )

    @work(thread=True, group="envio")
    def enviar_arquivo(self, destino: str, caminho: str, legenda: str | None = None) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                result = self.client.send_file(destino, caminho, caption=legenda)
        except Exception as exc:
            self.call_from_thread(self.erro, t("the file was not sent: {error}", error=exc))
            return
        self.call_from_thread(
            self.acao_concluida,
            t(
                "ok: attachment sent {ok}/{n} ({kb} KB)",
                ok=result.accepted,
                n=result.swarm_size,
                kb=(result.attachment_bytes or 0) // 1024,
            ),
        )

    @work(thread=True, group="envio")
    def enviar_digitando(self, destino: str) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                self.client.send_typing(destino)
        except Exception as exc:
            self.call_from_thread(self.log_rede, t("typing notice failed: {error}", error=exc))

    def enviar_anexo(self, caminho: Path, legenda: str | None = None) -> None:
        """Mostra o anexo na conversa e dispara o envio."""
        if not self.destino:
            self.erro(t("open a conversation first: /to <session_id>"))
            return
        tamanho = caminho.stat().st_size if caminho.is_file() else 0
        rotulo = t("[attachment] {name}", name=f"{caminho.name} ({tamanho / 1024:.0f} KB)")
        if legenda:
            rotulo += f" -- {legenda}"
        self.linha_mensagem(entrada=False, autor=t("you"), corpo=rotulo, ts=None)
        if caminho.suffix.lower() in imgview.EXTENSOES:
            self.mostrar_imagem(caminho, aviso=False)
        self.enviar_arquivo(self.destino, str(caminho), legenda)

    # --- anexos recebidos ---------------------------------------------------

    def mostrar_anexos(self, msg) -> None:
        """Desenha (se for imagem) e diz onde cada anexo baixado foi parar."""
        for anexo in msg.attachments:
            if not anexo.local_path:
                self.erro(t("{name}: could not download", name=anexo.descricao))
                continue
            self.ultimo_anexo = Path(anexo.local_path)
            if anexo.is_image and self.mostrar_imagem(anexo.local_path, aviso=False):
                self.sistema(t("saved in {path}  (/open shows it in the system)", path=anexo.local_path))
            else:
                self.sistema(t("file saved in {path}  (/open to open it)", path=anexo.local_path))

    def comando_baixar(self, arg: str = "") -> None:
        """Baixa o anexo que ficou esperando (o mais recente, ou o numero dado)."""
        if not self.pendentes:
            self.erro(t("no attachment waiting for download"))
            return
        indice = len(self.pendentes) - 1
        escolha = arg.strip()
        if escolha:
            if not escolha.isdigit() or not 1 <= int(escolha) <= len(self.pendentes):
                self.erro(t("usage: /download [1 to {n}]", n=len(self.pendentes)))
                return
            indice = int(escolha) - 1
        msg = self.pendentes.pop(indice)
        self.atualizar_status()
        self.sistema(t("downloading {what}...", what=", ".join(a.descricao for a in msg.attachments)))
        self.baixar_anexo(msg)

    @work(thread=True, group="baixar")
    def baixar_anexo(self, msg) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                self.client.fetch_attachments(msg)
        except Exception as exc:
            self.call_from_thread(self.erro, t("download failed: {error}", error=exc))
            return
        self.call_from_thread(self.mostrar_anexos, msg)

    def comando_abrir(self, arg: str) -> None:
        alvo: Path | None = None
        if arg.strip():
            alvo = imgview.parece_arquivo(arg)
            if not alvo:
                self.erro(t("file not found: {path}", path=arg))
                return
        elif self.ultimo_anexo and self.ultimo_anexo.is_file():
            alvo = self.ultimo_anexo
        elif self.client and self.client.profile:
            alvo = self.client.profile.attachments_dir
        if not alvo:
            self.erro(t("nothing to open yet"))
            return
        try:
            sistema.abrir_no_sistema(alvo)
            self.sistema(t("opening {name}", name=alvo.name))
        except Exception as exc:
            self.erro(t("could not open it: {error}", error=exc))

    # --- entrada do usuario -------------------------------------------------

    @on(Input.Submitted, "#entrada")
    def entrada_enviada(self, event: Input.Submitted) -> None:
        texto = event.value.strip()
        event.input.value = ""
        if not texto:
            return
        if texto.startswith("/") and not imgview.parece_arquivo(texto, so_absoluto=True):
            self.comando(texto)
            return
        if not self.client:
            self.erro(t("account not loaded yet"))
            return
        if not self.destino:
            self.erro(t("open a conversation first: /to <session_id>"))
            return

        # arquivo arrastado para o terminal: a linha e so o caminho (completo)
        arquivo = imgview.parece_arquivo(texto, so_absoluto=True)
        if arquivo:
            self.enviar_anexo(arquivo)
            return

        self.linha_mensagem(entrada=False, autor=t("you"), corpo=texto, ts=None)
        self.enviar(self.destino, texto)

    @on(ListView.Selected, "#conversas")
    def conversa_escolhida(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, ItemConversa):
            self.abrir_conversa(item.session_id)
        self.query_one("#entrada", Input).focus()

    @on(AbrirPerfil)
    def pedido_de_perfil(self, message: AbrirPerfil) -> None:
        self.abrir_cartao(message.session_id)

    @on(AbrirMeuPerfil)
    def pedido_de_meu_perfil(self, _message: AbrirMeuPerfil) -> None:
        self.abrir_meu_perfil()

    def abrir_meu_perfil(self) -> None:
        """Cartao da propria conta (avatar do topo, f3 ou /me)."""
        if not self.client:
            self.erro(t("account not loaded yet"))
            return

        def resolvido(resultado: tuple[str, str] | None) -> None:
            if not resultado:
                return
            acao, valor = resultado
            if acao == "nome" and self.client.profile:
                self.client.profile.display_name = valor or None
                self.atualizar_avatar()
                self.atualizar_status()
                self.sistema(t("your display name: {name}", name=valor or t("(none)")))
            elif acao == "senha":
                self.trocar_senha(tirar=valor == "tirar")
            elif acao == "killswitch":
                self.abrir_killswitch()
            elif acao == "idioma":
                self.trocar_idioma()
            elif acao == "apagar":
                self.comando_removeall()

        protegida = bool(self.client.profile and self.client.profile.is_protected())
        self.push_screen(
            MeuPerfil(
                self.client.session_id,
                self.client.display_name,
                self.client.identity.mnemonic,
                protegida=protegida,
            ),
            resolvido,
        )

    def trocar_senha(self, *, tirar: bool) -> None:
        """Liga ou desliga a protecao por senha do arquivo da conta."""
        if not (self.client and self.client.profile):
            return
        perfil = self.client.profile

        if tirar:

            def confirmou(senha: str | None) -> None:
                if not senha:
                    return
                try:
                    perfil.set_password(None, senha)
                except cofre.SenhaErrada:
                    self.erro(t("wrong password -- the protection stays on"))
                    return
                self.senha = None
                self.aviso(t("protection removed: the seed is in clear text again in account.json"))

            self.push_screen(
                PedirSenha(
                    t("remove the password"),
                    t(
                        "type the current password.\n\nwithout it, whoever can read the "
                        "account.json file gets your whole account."
                    ),
                    rotulo_ok=t("Remove password"),
                ),
                confirmou,
            )
            return

        def definiu(senha: str | None) -> None:
            if not senha:
                return
            try:
                perfil.set_password(senha, self.senha)
            except cofre.CofreError as exc:
                self.erro(t("could not protect it: {error}", error=exc))
                return
            self.senha = senha
            self.aviso(t("account protected: the seed is now encrypted with Argon2id + XChaCha20"))
            self.sistema(t("the password will be asked every time the interface opens"))
            self.sistema(t("the password cannot be recovered -- if you forget it, only the phrase saves the account"))
            if killswitch.carregar(perfil).avisar:
                self.aviso(t("note: with a password, the kill switch can no longer notify your contacts"))

        self.push_screen(
            PedirSenha(
                t("protect the account"),
                t(
                    "choose a password (at least 8 characters).\n\n"
                    "it encrypts the seed on disk with Argon2id + XChaCha20-Poly1305.\n"
                    "the password cannot be recovered: keep the recovery phrase too."
                ),
                confirmar=True,
                rotulo_ok=t("Protect"),
            ),
            definiu,
        )

    def abrir_killswitch(self) -> None:
        """Tela de configuracao do kill switch (/killswitch ou o perfil)."""
        if not (self.client and self.client.profile):
            self.erro(t("account not loaded yet"))
            return
        perfil = self.client.profile

        def resolvido(resultado: dict | None) -> None:
            if not resultado:
                return
            cfg: killswitch.Config = resultado["cfg"]
            try:
                killswitch.salvar(perfil, cfg)
            except (ValueError, OSError) as exc:
                self.erro(str(exc))
                return
            self._ks_prazo = killswitch.prazo(perfil, cfg)
            self.atualizar_status()
            if cfg.ativo:
                self.aviso(t("kill switch on: erases after {time} without access", time=cfg.descricao()))
                if cfg.avisar and perfil.is_protected():
                    self.aviso(t("note: with a password, the kill switch can no longer notify your contacts"))
            else:
                self.sistema(t("kill switch off"))
            self.ajustar_agendamento(cfg.ativo and resultado["agendar"])

        self.push_screen(
            ConfigKillSwitch(
                killswitch.carregar(perfil),
                ultimo=killswitch.ultimo_acesso(perfil),
                agendado=sistema.agendamento_instalado(perfil.path),
                protegida=perfil.is_protected(),
            ),
            resolvido,
        )

    @work(thread=True, exclusive=True, group="agendador")
    def ajustar_agendamento(self, instalar: bool) -> None:
        """Instala ou remove a verificacao de hora em hora no sistema."""
        if not (self.client and self.client.profile):
            return
        pasta = self.client.profile.path
        if instalar:
            try:
                como = sistema.instalar_agendamento(pasta)
            except RuntimeError as exc:
                self.call_from_thread(
                    self.erro, t("could not install the automatic check: {error}", error=exc)
                )
                return
            self.call_from_thread(self.sistema, t("automatic check installed: {how}", how=como))
        elif sistema.agendamento_instalado(pasta) and sistema.remover_agendamento(pasta):
            self.call_from_thread(self.sistema, t("automatic check removed"))

    def trocar_idioma(self, valor: str | None = None) -> None:
        """/lang en|pt, ou o botao do perfil (alterna)."""
        if valor:
            novo = i18n.normalizar(valor)
            if not novo:
                self.erro(t("unknown language: use en or pt"))
                return
        else:
            novo = "pt" if i18n.idioma() == "en" else "en"
        i18n.definir_idioma(novo)
        perfil = self.client.profile if self.client else None
        (perfil or Profile.open(self.profile_path)).atualizar_config(idioma=novo)
        self.atualizar_status()
        self.sistema(
            t(
                "language: {name} -- menus and shortcuts change the next time you open the app",
                name=i18n.NOMES[novo],
            )
        )

    def abrir_cartao(self, session_id: str | None = None) -> None:
        alvo = session_id or self.destino
        if not alvo:
            self.erro(t("open a conversation first"))
            return
        apelido = (
            self.client.profile.nickname(alvo) if self.client and self.client.profile else None
        )

        def resolvido(resultado: tuple[str, str] | None) -> None:
            if not resultado:
                return
            acao, valor = resultado
            if acao == "apelido" and self.client and self.client.profile:
                self.client.profile.set_nickname(alvo, valor or None)
                self.atualizar_conversas()
                self.atualizar_status()
                self.sistema(t("nickname of {sid}: {name}", sid=curto(alvo), name=valor or t("(none)")))
            elif acao == "mensagem":
                self.abrir_conversa(alvo)
            elif acao == "remover":
                self.remover_contato(alvo)

        self.push_screen(CartaoContato(alvo, apelido, None), resolvido)

    # --- comandos -----------------------------------------------------------

    def comando(self, linha: str) -> None:
        partes = linha.split(maxsplit=1)
        cmd = partes[0][1:].lower()
        arg = partes[1].strip() if len(partes) > 1 else ""

        if cmd in ("help", "ajuda", "h", "?"):
            self.action_ajuda()
        elif cmd in ("quit", "sair", "exit", "q"):
            self.exit()
        elif cmd in ("clear", "limpar"):
            self.action_limpar()
        elif cmd in ("to", "para", "d"):
            self.definir_destino(arg)
        elif cmd == "add":
            self.definir_destino(arg, trocar=False)
        elif cmd in ("profile", "perfil", "contact", "contato", "card"):
            self.abrir_cartao(arg.strip().lower() or None)
        elif cmd == "rm":
            self.remover_contato(arg or (self.destino or ""))
        elif cmd in ("me", "eu", "id", "account", "conta"):
            self.abrir_meu_perfil()
        elif cmd in ("phrase", "frase", "seed", "mnemonic"):
            if self.client:
                self.aviso(t("whoever has these words controls your account:"))
                self._write(Text(f"  {self.client.identity.mnemonic}", style="bold yellow"))
        elif cmd in ("name", "nome"):
            if self.client and self.client.profile:
                self.client.profile.display_name = arg or None
                self.sistema(t("your display name: {name}", name=arg or t("(none)")))
                self.atualizar_avatar()
                self.atualizar_status()
        elif cmd in ("nick", "apelido"):
            if self.client and self.client.profile and self.destino:
                self.client.profile.set_nickname(self.destino, arg or None)
                self.atualizar_conversas()
                self.atualizar_status()
                self.sistema(
                    t("nickname of {sid}: {name}", sid=curto(self.destino), name=arg or t("(none)"))
                )
            else:
                self.erro(t("open a conversation first"))
        elif cmd in ("poll", "buscar", "fetch"):
            self.action_poll()
        elif cmd in ("typing", "digitando"):
            if self.destino:
                self.enviar_digitando(self.destino)
                self.sistema(t("typing notice sent"))
            else:
                self.erro(t("open a conversation first"))
        elif cmd in ("img", "image", "file", "attach", "imagem", "anexo", "arquivo"):
            self.comando_img(arg)
        elif cmd in ("view", "show", "ver", "mostrar"):
            caminho = imgview.parece_arquivo(arg) if arg else None
            if caminho:
                self.sistema(f"{caminho.name}:")
                self.mostrar_imagem(caminho)
            else:
                self.erro(t("usage: /view <path of an image>"))
        elif cmd in ("open", "abrir"):
            self.comando_abrir(arg)
        elif cmd in ("paste", "colar"):
            self.action_colar()
        elif cmd in ("download", "baixar"):
            self.comando_baixar(arg)
        elif cmd == "auto":
            if arg in LIGAR + DESLIGAR:
                self.auto_baixar = arg in LIGAR
                self.sistema(
                    t("attachments will be downloaded automatically")
                    if self.auto_baixar
                    else t("I will ask before downloading attachments")
                )
            else:
                self.erro(t("usage: /auto on | /auto off"))
        elif cmd == "log":
            self.comando_log(arg)
        elif cmd in ("mode", "modo") and not arg:
            for linha_modo in i18n.longo("image_modes").splitlines():
                self.sistema(linha_modo)
            self.sistema(t("now: {mode}, width {width}", mode=self.modo_imagem, width=self.largura_imagem))
        elif cmd in ("mode", "modo"):
            modo = imgview.normalizar_modo(arg)
            if not modo:
                self.erro(t("modes: {modes}", modes=", ".join(imgview.MODOS)))
            elif modo in imgview.MODOS_GRAFICOS and not imgview.graficos_disponiveis():
                self.erro(
                    t(
                        "the '{mode}' mode must probe the terminal before the interface opens -- "
                        "close it and run: session-tui tui --mode {mode}",
                        mode=modo,
                    )
                )
            else:
                self.modo_imagem = modo
                self.sistema(t("images will be drawn in '{mode}' mode", mode=modo))
        elif cmd in ("width", "largura"):
            if arg.isdigit() and 8 <= int(arg) <= 200:
                self.largura_imagem = int(arg)
                self.sistema(t("image width: {n} cells", n=arg))
            else:
                self.erro(t("usage: /width <8 to 200>"))
        elif cmd == "onion":
            self.trocar_transporte(arg)
        elif cmd in ("network", "rede", "nodes", "nos"):
            self.estado_rede()
        elif cmd in ("protect", "proteger", "password", "senha"):
            self.trocar_senha(tirar=False)
        elif cmd in ("unprotect", "desproteger"):
            if self.client and self.client.profile and self.client.profile.is_protected():
                self.trocar_senha(tirar=True)
            else:
                self.erro(t("this account is not password-protected"))
        elif cmd in ("killswitch", "ks"):
            self.abrir_killswitch()
        elif cmd in ("lang", "language", "idioma"):
            if arg:
                self.trocar_idioma(arg)
            else:
                self.sistema(
                    t("language: {name} -- /lang en or /lang pt", name=i18n.NOMES[i18n.idioma()])
                )
        elif cmd in ("removeall", "apagartudo"):
            self.comando_removeall()
        else:
            self.erro(t("unknown command: /{cmd} (try /help)", cmd=cmd))

    def comando_log(self, arg: str) -> None:
        """/log liga ou desliga o relato da rede; /log <n> mostra o guardado."""
        escolha = arg.strip().lower()
        if escolha in ("clear", "limpar"):
            self._oculto.clear()
            self.atualizar_status()
            self.sistema(t("stored log discarded"))
            return
        if escolha.isdigit():
            recentes = list(self._oculto)[-max(1, int(escolha)) :]
            if not recentes:
                self.sistema(t("nothing stored"))
            for linha in recentes:
                self.sistema(linha)
            return
        if escolha in LIGAR:
            self.verboso = True
        elif escolha in DESLIGAR:
            self.verboso = False
        else:
            self.verboso = not self.verboso
        self.atualizar_status()
        self.sistema(
            t("network log on ({n} lines stored)", n=len(self._oculto))
            if self.verboso
            else t("network log hidden (/log turns it back on)")
        )

    def comando_img(self, arg: str) -> None:
        """/file <caminho> [legenda] -- aceita caminho entre aspas."""
        if not arg:
            self.erro(t("usage: /file <path> [caption]"))
            return
        if arg[0] in "\"'":
            fecha = arg.find(arg[0], 1)
            if fecha < 0:
                self.erro(t("unclosed quotes in the path"))
                return
            bruto, legenda = arg[: fecha + 1], arg[fecha + 1 :].strip()
        elif imgview.parece_arquivo(arg):  # o caminho inteiro e um arquivo
            bruto, legenda = arg, ""
        else:
            partes = arg.split(" ", 1)
            bruto, legenda = partes[0], (partes[1].strip() if len(partes) > 1 else "")

        caminho = imgview.parece_arquivo(bruto)
        if not caminho:
            self.erro(t("file not found: {path}", path=bruto))
            return
        self.enviar_anexo(caminho, legenda or None)

    def definir_destino(self, valor: str, *, trocar: bool = True) -> None:
        if not valor:
            self.erro(t("usage: /to <session_id>"))
            return
        try:
            keys.parse_session_id(valor)
        except keys.InvalidSessionID as exc:
            self.erro(str(exc))
            return
        session_id = valor.strip().lower()
        self.registrar_contato(session_id)
        if trocar:
            self.abrir_conversa(session_id)
        else:
            self.sistema(t("{sid} added to the list", sid=curto(session_id)))

    def remover_contato(self, session_id: str) -> None:
        if session_id in self.contatos:
            self.contatos.remove(session_id)
            self.nao_lidas.pop(session_id, None)
            if self.client and self.client.profile:
                self.client.profile.remove_contact(session_id)
            if self.destino == session_id:
                self.abrir_conversa(self.contatos[0] if self.contatos else None)
            else:
                self.atualizar_conversas()
            self.sistema(t("conversation removed: {sid}", sid=curto(session_id)))
        else:
            self.erro(t("that conversation is not in the list"))

    def trocar_transporte(self, arg: str) -> None:
        if not self.client:
            return
        if arg not in LIGAR + DESLIGAR:
            self.erro(t("usage: /onion on | /onion off"))
            return
        self.client.network.use_onion = arg in LIGAR
        self.atualizar_status()
        self.sistema(
            t("onion routing on (slower, hides your IP from the snodes)")
            if self.client.network.use_onion
            else t("onion routing off (direct connection to the snodes)")
        )

    @work(thread=True, exclusive=True, group="rede")
    def estado_rede(self) -> None:
        if not self.client:
            return
        try:
            with self._lock:
                pool = self.client.network.ensure_pool()
                agora = self.client.network.sync_clock()
                minha = self.client.network.get_swarm(self.client.session_id)
                destino_swarm = (
                    self.client.network.get_swarm(self.destino) if self.destino else []
                )
        except Exception as exc:
            self.call_from_thread(self.erro, t("could not query the network: {error}", error=exc))
            return
        linhas = [
            t("known service nodes: {n}", n=len(pool)),
            t("network clock: {ms} ms", ms=agora),
            t("my swarm: {n} nodes -- {nodes}", n=len(minha), nodes=", ".join(n.short for n in minha[:3])),
        ]
        if destino_swarm:
            linhas.append(
                t(
                    "destination swarm: {n} nodes -- {nodes}",
                    n=len(destino_swarm),
                    nodes=", ".join(n.short for n in destino_swarm[:3]),
                )
            )
        for linha in linhas:
            self.call_from_thread(self.sistema, linha)

    # --- apagar tudo e recomecar --------------------------------------------

    def comando_removeall(self) -> None:
        if not self.client:
            self.erro(t("account not loaded yet"))
            return
        self.push_screen(ConfirmarApagar(len(self.contatos)), self._removeall_confirmado)

    def _removeall_confirmado(self, resultado: dict | None) -> None:
        if not resultado:
            self.sistema(t("nothing was erased"))
            return
        self.aviso(t("erasing everything and creating a new account..."))
        self.apagar_tudo(bool(resultado.get("avisar")))

    @work(thread=True, group="apagar")
    def apagar_tudo(self, avisar: bool) -> None:
        """Avisa os contatos, apaga o perfil e cria uma conta nova.

        A ordem importa: o aviso sai pela conta ANTIGA (os contatos conhecem o
        ID antigo), e so depois o perfil e apagado.
        """
        if not self.client or not self.client.profile:
            return
        antigo = self.client
        nova = Identity.generate()
        avisados, falhas = 0, 0

        if avisar:
            texto = killswitch.MENSAGEM_MIGRACAO.format(novo=nova.session_id)
            for contato in list(self.contatos):
                try:
                    with self._lock:
                        antigo.send_text(contato, texto)
                    avisados += 1
                except Exception as exc:
                    falhas += 1
                    self.call_from_thread(
                        self.log_rede,
                        t("notice to {contact} failed: {error}", contact=curto(contato), error=exc),
                    )
            self.call_from_thread(
                self.sistema,
                t("migration notice: {ok} delivered, {failed} failed", ok=avisados, failed=falhas),
            )

        profile = antigo.profile
        apagados = profile.apagar_tudo()
        profile.save_identity(nova, self.senha)  # mantem a protecao por senha
        profile.state["anunciada"] = True
        profile.save_state()
        killswitch.registrar_acesso(profile, forcar=True)

        novo_cliente = SessionClient(
            nova,
            antigo.network,  # a lista de nos ja esta em memoria
            profile,
            log=lambda msg: self.call_from_thread(self.log_rede, msg),
        )
        self.call_from_thread(self._conta_trocada, novo_cliente, apagados)

    def _conta_trocada(self, novo: SessionClient, apagados: list[str]) -> None:
        self.client = novo
        self.contatos = []
        self.nao_lidas.clear()
        self.pendentes.clear()
        self.destino = None
        self.ultimo_anexo = None
        self._oculto.clear()
        chat = self.query_one("#chat", RichLog)
        chat.clear()
        self.aviso(t("erased: {files}", files=", ".join(apagados) if apagados else t("(nothing found)")))
        self._write(Text(""))
        self._write(Text(t("new account created"), style="bold"))
        self._write(Text(f"  {novo.session_id}", style="bold white"))
        self.aviso(t("SAVE THE RECOVERY PHRASE -- it is the only way to recover the account:"))
        self._write(Text(f"  {novo.identity.mnemonic}", style="bold yellow"))
        self._write(Text(""))
        self.sistema(t("start a conversation with /to <session_id>"))
        self.atualizar_conversas()
        self.atualizar_avatar()
        self.atualizar_status()

    # --- acoes de teclado ---------------------------------------------------

    def action_poll(self) -> None:
        if not self.pronto:
            self.erro(t("the network is not ready yet"))
            return
        self.buscar_mensagens(anunciar=True)

    def action_baixar(self) -> None:
        self.comando_baixar()

    def action_perfil(self) -> None:
        self.abrir_cartao()

    def action_meu_perfil(self) -> None:
        self.abrir_meu_perfil()

    def action_colar(self) -> None:
        """ctrl+v / ctrl+g: envia a imagem que esta na area de transferencia."""
        if not self.client:
            self.erro(t("account not loaded yet"))
            return
        if not self.destino:
            self.erro(t("open a conversation first: /to <session_id>"))
            return
        pasta = self.client.profile.path / "enviados" if self.client.profile else Path(".")
        try:
            caminho = imgview.da_area_de_transferencia(pasta)
        except imgview.ImagemError as exc:
            self.erro(str(exc))
            return
        if not caminho:
            self.erro(t("there is no image in the clipboard"))
            return
        self.enviar_anexo(caminho)

    def action_limpar(self) -> None:
        self.query_one("#chat", RichLog).clear()
        if self.destino:
            self.cabecalho_conversa(self.destino)

    def action_ajuda(self) -> None:
        if isinstance(self.screen, AjudaModal):
            return
        self.push_screen(AjudaModal())


def run(
    profile_path: str | Path = "session_profile",
    *,
    use_onion: bool = False,
    destino: str | None = None,
    modo_imagem: str = "half",
) -> None:
    # A sondagem do terminal (sixel/kitty) tem que acontecer aqui, antes de o
    # Textual tomar conta do stdin -- feita com a TUI no ar, embaralha a tela.
    if modo_imagem in imgview.MODOS_GRAFICOS and not imgview.preparar_graficos():
        print(t("  could not probe the terminal; using half-blocks"))
        modo_imagem = "half"
    SessionTUI(
        profile_path, use_onion=use_onion, destino=destino, modo_imagem=modo_imagem
    ).run()
