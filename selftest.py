"""Testes do cliente: formato das mensagens (offline) e rede real (online).

    python selftest.py            # so offline: cripto, padding, protobuf, kill switch
    python selftest.py --network  # inclui ida e volta real pela rede Session
    python selftest.py --network --onion   # idem, usando onion routing
"""

from __future__ import annotations

import ast
import json
import string
import sys
import tempfile
import time
from pathlib import Path

import imgview
from session_native import attachments, cofre, i18n, keys, killswitch, mnemonic, proto, sistema, wire
from session_native.client import SessionClient
from session_native.keys import Identity
from session_native.profile import HistoryEntry, Profile
from session_native.snode import SnodeNetwork

OK = "[ok]"
FAIL = "[--]"
RAIZ = Path(__file__).resolve().parent


def _cifrar_formato_novo(dados: bytes, chave: bytes, *, padding: int = 7) -> bytes:
    """Monta um anexo no formato novo da libsession, para testar a leitura.

    'S' | header | chunks(32 KiB) do stream; o texto em claro comeca com
    (padding-1) zeros e um 0x01 antes dos dados.
    """
    from nacl import bindings as sodium

    estado = sodium.crypto_secretstream_xchacha20poly1305_state()
    header = sodium.crypto_secretstream_xchacha20poly1305_init_push(estado, chave)
    claro = b"\x00" * (padding - 1) + b"\x01" + dados

    saida = bytearray(b"S" + header)
    for inicio in range(0, len(claro), attachments.STREAM_CHUNK):
        pedaco = claro[inicio : inicio + attachments.STREAM_CHUNK]
        ultimo = inicio + attachments.STREAM_CHUNK >= len(claro)
        saida += sodium.crypto_secretstream_xchacha20poly1305_push(
            estado,
            pedaco,
            None,
            sodium.crypto_secretstream_xchacha20poly1305_TAG_FINAL if ultimo else 0,
        )
    return bytes(saida)


def _png_de_teste(destino: Path, tamanho: tuple[int, int] = (16, 12)) -> bool:
    """Cria um PNG de verdade; devolve False se o Pillow nao estiver instalado."""
    try:
        from PIL import Image as PILImage
    except ImportError:
        destino.write_bytes(b"nao-e-png")
        return False
    img = PILImage.new("RGB", tamanho, (20, 120, 200))
    for x in range(tamanho[0]):
        img.putpixel((x, x % tamanho[1]), (250, 210, 60))
    img.save(destino)
    return True


def _campos(texto: str) -> set[str]:
    return {nome for _, nome, _, _ in string.Formatter().parse(texto) if nome}


def _textos_traduziveis() -> tuple[list[tuple[str, str]], list[str]]:
    """Todos os t("...") do codigo-fonte, e as chamadas que nao sao literais."""
    arquivos = [RAIZ / "main.py", RAIZ / "tui.py", RAIZ / "imgview.py"]
    arquivos += sorted((RAIZ / "session_native").glob("*.py"))
    textos: list[tuple[str, str]] = []
    problemas: list[str] = []
    for arquivo in arquivos:
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "t"):
                continue
            if not no.args:
                continue
            primeiro = no.args[0]
            if isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
                textos.append((primeiro.value, f"{arquivo.name}:{no.lineno}"))
            elif not isinstance(primeiro, ast.Name):  # t(variavel) e aceito; f-string nao
                problemas.append(f"{arquivo.name}:{no.lineno}")
    return textos, problemas


def testar_traducoes() -> bool:
    """Todo t("...") tem traducao em portugues, com os mesmos {campos}."""
    from session_native.traducao_pt import LONGOS_PT, PT

    if not (RAIZ / "tui.py").is_file():
        print("     . source files not available (packaged build); skipping")
        return True
    textos, problemas = _textos_traduziveis()
    ok = True
    for local in problemas:
        print(f"{FAIL} i18n       : t() with a non-literal text at {local}")
        ok = False
    faltando = sorted({(texto, local) for texto, local in textos if texto not in PT})
    for texto, local in faltando[:20]:
        print(f"{FAIL} i18n       : no Portuguese for {texto!r} ({local})")
    if faltando:
        ok = False
    for texto, local in textos:
        if texto in PT and _campos(texto) != _campos(PT[texto]):
            print(f"{FAIL} i18n       : fields differ in {texto!r} ({local})")
            ok = False
    if set(LONGOS_PT) != set(i18n.LONGOS_EN):
        print(f"{FAIL} i18n       : long texts differ: {set(LONGOS_PT) ^ set(i18n.LONGOS_EN)}")
        ok = False
    if ok:
        print(f"{OK} i18n       : {len({x for x, _ in textos})} texts, all translated to Portuguese")
    return ok


def testar_killswitch(bob: Identity) -> bool:
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        perfil = Profile.open(Path(tmp) / "ks")
        velho = Identity.generate()
        perfil.save_identity(velho)
        perfil.add_contact(bob.session_id)
        perfil.append_history(HistoryEntry("out", bob.session_id, 1, body="oi"))

        cfg = killswitch.Config(ativo=True, quantidade=2, unidade="hours", nova_conta=True)
        killswitch.salvar(perfil, cfg)
        assert not killswitch.vencido(perfil)
        assert killswitch.vencido(perfil, agora=time.time() + 2 * 3600 + 5)
        assert not killswitch.vencido(perfil, agora=time.time() - 3600)  # relogio voltou
        print(f"{OK} killswitch : 2 hours without access -> expired; before that, not")

        perfil.atualizar_config(ultimo_acesso=time.time() - 3 * 3600, idioma="pt")
        disparo = killswitch.verificar(perfil)
        assert disparo is not None and disparo.novo_id
        assert disparo.novo_id != velho.session_id
        assert Profile.open(perfil.path).load_identity().session_id == disparo.novo_id
        assert not perfil.history_path.exists()
        assert Profile.open(perfil.path).contacts == []
        assert killswitch.carregar(perfil).ativo  # a configuracao sobrevive
        assert perfil.ler_config().get("idioma") == "pt"
        assert not killswitch.vencido(perfil)  # a conta nova comeca a contar agora
        assert killswitch.ultimo_disparo(perfil) is not None
        killswitch.marcar_visto(perfil)
        assert killswitch.ultimo_disparo(perfil) is None
        print(f"{OK} killswitch : fired -> account, history and contacts erased, new account created")

        # conta protegida + avisar: nao ha chave para assinar o aviso, apaga mesmo assim
        perfil.set_password("senha-de-teste-1")
        perfil.add_contact(bob.session_id)
        killswitch.salvar(perfil, killswitch.Config(ativo=True, quantidade=1, unidade="days", avisar=True, nova_conta=False))
        perfil.atualizar_config(ultimo_acesso=time.time() - 2 * 86400)
        disparo = killswitch.verificar(perfil)
        assert disparo is not None and disparo.aviso_pulado and disparo.avisados == 0
        assert not perfil.has_account() and disparo.novo_id is None
        assert not killswitch.vencido(perfil)  # sem conta, nada a vigiar
        print(f"{OK} killswitch : protected account -> notice skipped, erased, no new account")

    for bruto, esperado in (("dias", "days"), ("h", "hours"), ("meses", "months"), ("years", "years"), ("x", None)):
        if killswitch.normalizar_unidade(bruto) != esperado:
            print(f"{FAIL} killswitch : unit {bruto!r} -> {killswitch.normalizar_unidade(bruto)!r}")
            ok = False
    for invalida in (killswitch.Config(quantidade=0), killswitch.Config(quantidade=101, unidade="years")):
        try:
            invalida.validar()
            print(f"{FAIL} killswitch : accepted {invalida.descricao()}")
            ok = False
        except ValueError:
            pass
    if ok:
        print(f"{OK} killswitch : units in English/Portuguese; 0 and 101 years rejected")
    return ok


def offline() -> bool:
    print("== offline tests ==")
    ok = True

    # 1. identidade e frase de recuperacao
    alice = Identity.generate()
    assert len(alice.session_id) == 66 and alice.session_id.startswith("05")
    assert len(alice.mnemonic.split()) == 13
    assert Identity.from_mnemonic(alice.mnemonic).session_id == alice.session_id
    assert mnemonic.decode(mnemonic.encode(bytes(range(16)))) == bytes(range(16))
    print(f"{OK} identity   : {alice.session_id}")
    print(f"{OK} phrase     : the 13 words go back to the same Session ID")

    # seed conhecido -> resultado estavel (detecta mudanca na derivacao)
    fixed = Identity.from_seed(bytes.fromhex("000102030405060708090a0b0c0d0e0f"))
    print(f"{OK} fixed seed : {fixed.session_id}")
    print(f"     phrase    : {fixed.mnemonic}")

    # 2. padding de 160 bytes com terminador 0x80
    for size in (0, 1, 10, 159, 160, 161, 500, 4096):
        padded = wire.pad_message(b"x" * size)
        assert len(padded) % wire.PADDING_MULTIPLE == 0, (size, len(padded))
        assert padded[size] == wire.PADDING_TERMINATOR
        assert wire.unpad_message(padded) == b"x" * size
    print(f"{OK} padding    : multiples of 160 B, 0x80 terminator, reversible")

    # 3. ida e volta da criptografia 1-para-1
    bob = Identity.generate()
    sent_at = 1_700_000_000_000
    content = wire.build_content(body="hello from the terminal", timestamp_ms=sent_at, display_name="Alice")
    payload = wire.encode_outgoing(alice, bob.x25519_pk, content, sent_at)
    message = wire.decode_incoming(bob, payload)
    assert message.body == "hello from the terminal"
    assert message.sender == alice.session_id  # remetente provado pela assinatura
    assert message.display_name == "Alice"
    assert message.timestamp_ms == sent_at
    print(f"{OK} crypto     : {len(payload)} B on the wire, sender authenticated")

    # 4. um terceiro nao abre a caixa selada
    try:
        wire.decode_incoming(Identity.generate(), payload)
        print(f"{FAIL} a third party decrypted it!")
        ok = False
    except Exception:
        print(f"{OK} secrecy    : a third party cannot decrypt")

    # 5. adulteracao e rejeitada
    tampered = bytearray(payload)
    tampered[-1] ^= 0xFF
    try:
        wire.decode_incoming(bob, bytes(tampered))
        print(f"{FAIL} a tampered message was accepted!")
        ok = False
    except Exception:
        print(f"{OK} integrity  : one changed byte -> rejected")

    # 6. protobuf: numeros de campo iguais aos do SessionProtos.proto
    websocket = proto.decode(payload)
    assert websocket[wire.WS_TYPE][0] == wire.WS_TYPE_REQUEST
    request = proto.get_msg(websocket, wire.WS_REQUEST) or {}
    envelope = proto.decode(bytes(proto.get(request, wire.WS_REQ_BODY)))
    assert envelope[wire.ENVELOPE_TYPE][0] == wire.ENVELOPE_TYPE_SESSION_MESSAGE
    assert envelope[wire.ENVELOPE_TIMESTAMP][0] == sent_at
    assert len(proto.get(envelope, wire.ENVELOPE_PRO_SIG)) == 64
    assert wire.ENVELOPE_CONTENT in envelope
    print(f"{OK} protobuf   : WebSocketMessage > Envelope(type=6) > sealed box")

    # 7. anexos: padding, cripto e AttachmentPointer
    original = bytes(range(256)) * 7  # 1792 B
    cifrado = attachments.encrypt_attachment(original)
    assert len(cifrado.key) == 64 and len(cifrado.digest) == 32
    assert cifrado.plain_size == len(original)
    assert attachments.decrypt_attachment(
        cifrado.blob, cifrado.key, digest=cifrado.digest, size=cifrado.plain_size
    ) == original
    print(
        f"{OK} attachment : {len(original)} B -> {len(cifrado.blob)} B encrypted "
        "(AES-CBC + HMAC), comes back equal"
    )

    for chave_errada in (b"\x00" * 64,):
        try:
            attachments.decrypt_attachment(cifrado.blob, chave_errada, size=len(original))
            print(f"{FAIL} attachment with the wrong key was accepted!")
            ok = False
        except attachments.AttachmentError:
            pass
    quebrado = bytearray(cifrado.blob)
    quebrado[20] ^= 0xFF
    try:
        attachments.decrypt_attachment(
            bytes(quebrado), cifrado.key, digest=cifrado.digest, size=len(original)
        )
        print(f"{FAIL} tampered attachment was accepted!")
        ok = False
    except attachments.AttachmentError:
        pass
    print(f"{OK} attachment : wrong key and changed bytes are rejected")

    # formato novo (crypto_secretstream, chave de 32 B) -- o que o app oficial manda
    chave32 = bytes(range(32))
    cifrado_novo = _cifrar_formato_novo(original, chave32)
    assert attachments.decrypt_any(cifrado_novo, chave32) == original
    assert attachments.decrypt_stream_attachment(cifrado_novo, chave32) == original
    try:
        attachments.decrypt_any(cifrado_novo, bytes(32))
        print(f"{FAIL} new-format attachment with the wrong key was accepted!")
        ok = False
    except attachments.AttachmentError:
        pass
    try:
        attachments.decrypt_stream_attachment(b"X" + cifrado_novo[1:], chave32)
        print(f"{FAIL} accepted a wrong format marker!")
        ok = False
    except attachments.AttachmentError:
        pass
    print(
        f"{OK} new format : xchacha20 stream of {len(cifrado_novo)} B decrypted "
        "(what current clients send)"
    )

    pointer = wire.build_attachment_pointer(
        url="https://filev2.getsession.org/file/123",
        attachment_id=123,
        content_type="image/png",
        key=cifrado.key,
        digest=cifrado.digest,
        size=cifrado.plain_size,
        file_name="foto.png",
        width=800,
        height=600,
    )
    lido = wire.parse_attachment_pointer(pointer)
    assert lido.url.endswith("/file/123") and lido.attachment_id == 123
    assert lido.key == cifrado.key and lido.size == len(original)
    assert lido.width == 800 and lido.height == 600 and lido.is_image
    conteudo = wire.build_content(body="look at the photo", timestamp_ms=1, attachments=[pointer])
    msg = wire.decode_incoming(
        bob, wire.encode_outgoing(alice, bob.x25519_pk, conteudo, 1)
    )
    assert len(msg.attachments) == 1 and msg.attachments[0].file_name == "foto.png"
    assert msg.body == "look at the photo"
    print(f"{OK} pointer    : url/key/digest/size/dimensions survive the round trip")

    # 8. caminhos arrastados para o terminal / colados
    with tempfile.TemporaryDirectory() as tmp:
        foto = Path(tmp) / "my photo.png"
        png_real = _png_de_teste(foto)
        texto = Path(tmp) / "note.txt"
        texto.write_text("hi", encoding="utf-8")

        assert imgview.parece_imagem(str(foto)) == foto
        assert imgview.parece_imagem(f'"{foto}"  ') == foto  # com aspas, como o terminal solta
        assert imgview.parece_imagem(foto.as_uri()) == foto  # file:///C:/...%20...
        assert imgview.parece_imagem("hi, how are you?") is None
        assert imgview.parece_imagem(str(texto)) is None  # txt nao e imagem
        assert imgview.parece_arquivo(str(texto)) == texto  # mas e um arquivo
        assert imgview.parece_arquivo("an ordinary message") is None
        assert imgview.parece_arquivo("note.txt", so_absoluto=True) is None  # mensagem, nao arquivo
        if sistema.NOME == "linux":  # GNOME/kitty soltam "my\ photo.png"
            assert imgview.parece_imagem(str(foto).replace(" ", "\\ ")) == foto
        print(f"{OK} drag-drop  : raw, quoted and file:// paths are recognized")

        if png_real:
            assert imgview.renderizar(foto, largura=8, modo="half") is not None
            assert imgview.renderizar(foto, largura=8, modo="meio") is not None  # apelido antigo
            assert imgview.dimensoes(foto) == (16, 12)
            print(f"{OK} drawing    : image converted to half-blocks for the terminal")
            try:
                imgview.renderizar(texto)
                print(f"{FAIL} accepted a .txt as an image")
                ok = False
            except imgview.ImagemError:
                print(f"{OK} drawing    : a file that is not an image is refused")
        else:
            print("     . Pillow not installed; skipping the terminal drawing")

    # 9. protecao da conta por senha
    with tempfile.TemporaryDirectory() as tmp:
        perfil = Profile.open(Path(tmp) / "p")
        identidade = Identity.generate()
        perfil.save_identity(identidade)
        assert not perfil.is_protected()
        bruto = (perfil.account_path).read_text(encoding="utf-8")
        assert identidade.seed.hex() in bruto, "the seed should be in clear text before"

        perfil.set_password("a-good-password-123")
        bruto = perfil.account_path.read_text(encoding="utf-8")
        assert perfil.is_protected()
        assert identidade.seed.hex() not in bruto, "the seed leaked into the protected file!"
        assert identidade.mnemonic.split()[0] not in bruto, "the phrase leaked!"
        assert perfil.account_session_id() == identidade.session_id  # publico, fica em claro
        print(f"{OK} vault      : seed and phrase leave the disk; Session ID stays readable")

        assert perfil.load_identity("a-good-password-123").session_id == identidade.session_id
        for errada in ("a-good-password-124", "", "A-GOOD-PASSWORD-123"):
            try:
                perfil.load_identity(errada or None)
                print(f"{FAIL} opened the account with the password {errada!r}")
                ok = False
            except (cofre.SenhaErrada, cofre.SenhaNecessaria):
                pass
        print(f"{OK} vault      : only the right password opens it; wrong and empty are refused")

        # trocar e tirar a senha
        perfil.set_password("another-good-one", "a-good-password-123")
        assert perfil.load_identity("another-good-one").seed == identidade.seed
        perfil.set_password(None, "another-good-one")
        assert not perfil.is_protected()
        assert perfil.load_identity().seed == identidade.seed
        print(f"{OK} vault      : changing and removing the password keep the same account")

        # bloco cifrado muda a cada gravacao (sal e nonce novos)
        perfil.set_password("same-password-here")
        primeiro = json.loads(perfil.account_path.read_text(encoding="utf-8"))["dados"]
        perfil.set_password("same-password-here", "same-password-here")
        segundo = json.loads(perfil.account_path.read_text(encoding="utf-8"))["dados"]
        assert primeiro != segundo, "salt/nonce repeated between writes"
        print(f"{OK} vault      : every write uses a new salt and nonce")

    # 10. Session IDs invalidos sao recusados
    for bad_id in ("05abc", "a" * 66, "03" + "a" * 64, ""):
        try:
            keys.parse_session_id(bad_id)
            print(f"{FAIL} accepted an invalid Session ID: {bad_id[:12]}")
            ok = False
        except keys.InvalidSessionID:
            pass
    print(f"{OK} validation : invalid Session IDs refused")

    # 11. kill switch e 12. traducoes
    ok = testar_killswitch(bob) and ok
    ok = testar_traducoes() and ok
    return ok


def online(use_onion: bool = False) -> bool:
    modo = "onion (3 hops)" if use_onion else "direct"
    print(f"\n== real network test ({modo}) ==")
    log = lambda msg: print(f"     . {msg}")

    network = SnodeNetwork(use_onion=use_onion, log=log)
    pool = network.ensure_pool()
    print(f"{OK} snodes     : {len(pool)} known nodes")

    now = network.sync_clock()
    print(f"{OK} clock      : network at {now} ms")

    alice, bob = Identity.generate(), Identity.generate()
    temporario = Path(tempfile.mkdtemp(prefix="session_selftest_"))
    client_a = SessionClient(alice, network, Profile.open(temporario / "alice"), log=log)
    client_b = SessionClient(bob, network, Profile.open(temporario / "bob"), log=log)
    print(f"     alice     : {alice.session_id}")
    print(f"     bob       : {bob.session_id}")

    swarm = network.get_swarm(bob.session_id)
    print(f"{OK} bob swarm  : {len(swarm)} nodes ({swarm[0].short}, ...)")

    text = f"automatic test {int(time.time())}"
    result = client_a.send_text(bob.session_id, text)
    print(
        f"{OK} sent       : {result.accepted}/{result.swarm_size} nodes accepted, "
        f"{result.size_bytes} B, hash {str(result.hash)[:12]}..."
    )
    if not result.ok:
        print(f"{FAIL} no swarm node stored the message")
        return False

    # o hash devolvido pelo snode e blake2b(pubkey || namespace || data):
    # se ele bate com o nosso calculo, o no guardou exatamente os bytes enviados
    if result.hash_matches:
        print(f"{OK} integrity  : the snode's hash matches the local calculation")
    else:
        print(f"{FAIL} the snode's hash differs from the local calculation (diagnostic only)")

    chegou = False
    for attempt in range(6):
        inbox = client_b.poll()
        received = [m for m in inbox if m.body == text]
        if received:
            msg = received[0]
            print(f"{OK} received   : {msg.body!r}")
            print(f"{OK} sender     : {msg.sender}")
            assert msg.sender == alice.session_id
            chegou = True
            break
        time.sleep(2)
        print(f"     . attempt {attempt + 1}: nothing yet, waiting...")

    if not chegou:
        print(f"{FAIL} the message did not come back in the polling")
        return False

    return imagem(client_a, client_b, temporario, modo)


def imagem(client_a: SessionClient, client_b: SessionClient, pasta: Path, modo: str) -> bool:
    """Envia uma imagem de verdade pelo file server e confere os bytes."""
    print(f"\n-- image attachment ({modo}) --")
    try:
        from PIL import Image as PILImage
    except ImportError:
        print("     . Pillow not installed; skipping the image test")
        return True

    caminho = pasta / "test.png"
    img = PILImage.new("RGB", (96, 64), (30, 120, 200))
    for x in range(96):
        img.putpixel((x, x % 64), (250, 240, 60))
    img.save(caminho)
    original = caminho.read_bytes()

    result = client_a.send_file(
        client_b.session_id, caminho, caption="automatic test image"
    )
    print(
        f"{OK} sent       : {len(original)} B -> {result.attachment_bytes} B encrypted "
        f"on the file server, {result.accepted}/{result.swarm_size} nodes"
    )
    print(f"     url       : {result.attachment_url}")
    if not result.ok:
        print(f"{FAIL} the message with the attachment was not stored")
        return False

    for attempt in range(8):
        for msg in client_b.poll():
            if not msg.attachments:
                continue
            anexo = msg.attachments[0]
            print(f"{OK} received   : {anexo.descricao}  caption={msg.body!r}")
            if not anexo.local_path:
                print(f"{FAIL} the attachment was not saved to disk")
                return False
            baixado = Path(anexo.local_path).read_bytes()
            if baixado != original:
                print(f"{FAIL} different bytes: {len(baixado)} vs {len(original)}")
                return False
            print(f"{OK} integrity  : {len(baixado)} B identical to the original")
            print(f"     saved in  : {anexo.local_path}")
            print(f"\n{OK} THE IMAGE MADE THE ROUND TRIP ({modo})")
            return True
        time.sleep(2)
        print(f"     . attempt {attempt + 1}: attachment not here yet...")

    print(f"{FAIL} the attachment did not come back in the polling")
    return False


def main() -> int:
    args = sys.argv[1:]
    ok = offline()
    if "--network" in args or "--rede" in args:
        ok = online(use_onion="--onion" in args) and ok
    print("\nRESULT:", "all passed" if ok else "there were failures")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
