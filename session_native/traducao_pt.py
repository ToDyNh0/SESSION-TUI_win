"""Traducao para portugues: texto em ingles (a chave) -> texto em portugues.

Os `{campos}` precisam ser os mesmos dos dois lados -- o selftest confere.
Texto que faltar aqui sai em ingles.
"""

PT = {
    # --- geral --------------------------------------------------------------
    "yes": "sim",
    "no": "não",
    "phrase": "frase",
    "you": "você",
    "(none)": "(nenhum)",
    "(no name)": "(sem nome)",
    "(nothing found)": "(nada encontrado)",
    "attachment": "anexo",
    "command": "comando",
    "hour": "hora",
    "hours": "horas",
    "day": "dia",
    "days": "dias",
    "month": "mês",
    "months": "meses",
    "year": "ano",
    "years": "anos",
    "ERASE": "APAGAR",
    "onion (3 hops)": "onion (3 saltos)",
    "direct": "direto",
    "{n} nodes": "{n} nós",
    "{when} (in {time})": "{when} (em {time})",
    # --- linha de comando: conta -------------------------------------------
    "  SAVE THE PHRASE: it is the only way to recover the account.": "  GUARDE A FRASE: ela é a única forma de recuperar a conta.",
    "  account created": "  conta criada",
    "  account created in {path}": "  conta criada em {path}",
    "  (also saved in {path})": "  (salva também em {path})",
    "  account imported": "  conta importada",
    "  invalid phrase: {error}": "  frase inválida: {error}",
    "  there is already an account in this profile (use --force to replace it)": "  já existe uma conta nesse perfil (use --force para substituir)",
    "  no account in {path}": "  nenhuma conta em {path}",
    "  the account is password-protected and there is no terminal to ask.\n  use --password PASSWORD (careful: it stays in the shell history)": "  a conta é protegida por senha e não há terminal para perguntar.\n  use --password SENHA (atenção: fica no histórico do shell)",
    "  account password: ": "  senha da conta: ",
    "\n  no password, nothing to do": "\n  sem senha, nada a fazer",
    "  this account is already protected (use `unprotect` to remove it)": "  esta conta já está protegida (use `unprotect` para tirar)",
    "  new password: ": "  nova senha: ",
    "  repeat the password: ": "  repita a senha: ",
    "  current password: ": "  senha atual: ",
    "  use at least 8 characters": "  use pelo menos 8 caracteres",
    "  the passwords do not match": "  as senhas não batem",
    "  failed: {error}": "  falhou: {error}",
    "  wrong password": "  senha incorreta",
    "  account protected: the seed is now encrypted (Argon2id + XChaCha20-Poly1305)": "  conta protegida: o seed agora fica cifrado (Argon2id + XChaCha20-Poly1305)",
    "  the password will be asked every time the profile is opened": "  a senha será pedida sempre que o perfil for aberto",
    "  there is no way to recover the password -- keep the recovery phrase too": "  não há como recuperar a senha -- guarde também a frase de recuperação",
    "  this account is not protected": "  esta conta não está protegida",
    "  protection removed: the seed is in clear text again in account.json": "  proteção removida: o seed voltou a ficar em claro em account.json",
    "  note: with a password, the kill switch can no longer notify your contacts": "  obs.: com senha, o kill switch não consegue mais avisar seus contatos",
    # --- linha de comando: mensagens ----------------------------------------
    "  sent: {ok}/{n} swarm nodes stored it ({size} B)": "  enviado: {ok}/{n} nós da swarm guardaram ({size} B)",
    "  sent: {ok}/{n} swarm nodes stored it": "  enviado: {ok}/{n} nós da swarm guardaram",
    "  attachment: {n} B encrypted on the file server": "  anexo: {n} B cifrados no file server",
    "  invalid destination: {error}": "  destino inválido: {error}",
    "  sending failed: {error}": "  falha no envio: {error}",
    "  warning: the snode's hash does not match the local calculation": "  aviso: o hash do snode não confere com o cálculo local",
    "  this terminal did not answer the probe; using half-blocks": "  este terminal não respondeu à sondagem; usando meio-blocos",
    "  could not probe the terminal; using half-blocks": "  não consegui sondar o terminal; usando meio-blocos",
    "  listening on {sid}": "  ouvindo em {sid}",
    "  (every {s}s, ctrl+c to quit)": "  (a cada {s}s, ctrl+c para sair)",
    "           [attachment] {desc}": "           [anexo] {desc}",
    "           saved in {path}": "           salvo em {path}",
    "           from {sid}": "           de {sid}",
    "  . network: {error}": "  . rede: {error}",
    "\n  bye": "\n  fim",
    "known service nodes": "service nodes conhecidos",
    "network clock": "relógio da rede",
    "transport": "transporte",
    "my swarm": "minha swarm",
    "destination swarm": "swarm do destino",
    # --- linha de comando: idioma -------------------------------------------
    "  language saved: {name}": "  idioma salvo: {name}",
    "  language: {name}": "  idioma: {name}",
    "  options: en (English), pt (Português)": "  opções: en (English), pt (Português)",
    "  unknown language: use en or pt": "  idioma desconhecido: use en ou pt",
    # --- linha de comando: kill switch --------------------------------------
    "  KILL SWITCH FIRED on {when}": "  KILL SWITCH DISPAROU em {when}",
    "  erased: {files}": "  apagado: {files}",
    "  kill switch: no access for more than {time} -- erasing everything...": "  kill switch: mais de {time} sem acesso -- apagando tudo...",
    "  contacts NOT notified: {reason}": "  contatos NÃO avisados: {reason}",
    "  notice sent to {ok} of {n} contact(s) ({failed} failed)": "  aviso entregue a {ok} de {n} contato(s) ({failed} falharam)",
    "  new account: {sid}": "  conta nova: {sid}",
    "  no new account was created": "  nenhuma conta nova foi criada",
    "  kill switch ON: erases after {time} without access": "  kill switch LIGADO: apaga depois de {time} sem acesso",
    "  kill switch OFF": "  kill switch DESLIGADO",
    "last access": "último acesso",
    "erases at": "apaga em",
    "notify contacts": "avisar contatos",
    "create new account": "criar conta nova",
    "automatic check": "verificação automática",
    "installed (every hour)": "instalada (de hora em hora)",
    "not installed": "não instalada",
    "last fired": "último disparo",
    "  note: a password-protected account cannot notify contacts when the": "  obs.: conta protegida por senha não consegue avisar os contatos quando o",
    "  kill switch fires -- the key that signs the notice is locked": "  kill switch dispara -- a chave que assina o aviso está trancada",
    "  automatic check installed: {how}": "  verificação automática instalada: {how}",
    "  could not install the automatic check: {error}": "  não deu para instalar a verificação automática: {error}",
    "  automatic check removed": "  verificação automática removida",
    "  there was no automatic check installed": "  não havia verificação automática instalada",
    "  turn the kill switch on first: killswitch on --after 30 --unit days": "  ligue o kill switch antes: killswitch on --after 30 --unit days",
    "  the command was not run: the account it would use was erased": "  o comando não foi executado: a conta que ele usaria foi apagada",
    "unknown unit: use hours, days, months or years": "unidade desconhecida: use horas, dias, meses ou anos",
    "the time must be at least 1": "o tempo precisa ser pelo menos 1",
    "the time can be at most 100 years": "o tempo pode ser no máximo 100 anos",
    "the account is password-protected, so the key that signs the notice is locked": "a conta é protegida por senha, então a chave que assina o aviso está trancada",
    "notifying {n} contact(s)...": "avisando {n} contato(s)...",
    "notice to {contact} failed: {error}": "aviso para {contact} falhou: {error}",
    # --- linha de comando: ajuda do argparse --------------------------------
    "unknown mode: {mode} (options: {modes})": "modo desconhecido: {mode} (opções: {modes})",
    "account folder (default: {path})": "pasta da conta (padrão: {path})",
    "3-hop onion routing": "roteamento onion em 3 saltos",
    "shows network details": "mostra detalhes da rede",
    "password of the protected account (asked if missing)": "senha da conta protegida (perguntada se faltar)",
    "interface language for this run: en or pt": "idioma da interface nesta execução: en ou pt",
    "native terminal Session client (your own account, no official app)": "cliente Session nativo de terminal (conta própria, sem o app oficial)",
    "live terminal interface (default)": "interface ao vivo no terminal (padrão)",
    "Session ID of the first conversation": "Session ID da primeira conversa",
    "how to draw images: {modes}": "como desenhar imagens: {modes}",
    "creates a new account": "cria uma conta nova",
    "replaces the existing account": "substitui a conta existente",
    "recovers an account from the 13-word phrase": "recupera uma conta pela frase de 13 palavras",
    "the 13 words, in quotes": "as 13 palavras, entre aspas",
    "encrypts the account seed with a password": "cifra o seed da conta com uma senha",
    "removes the account password": "tira a senha da conta",
    "shows your Session ID": "mostra seu Session ID",
    "also shows the recovery phrase": "mostra também a frase de recuperação",
    "sends a message and exits": "envia uma mensagem e sai",
    "destination Session ID (05...)": "Session ID de destino (05...)",
    "the message text": "o texto da mensagem",
    "sends an image or file and exits": "envia uma imagem ou arquivo e sai",
    "path of the file": "caminho do arquivo",
    "optional caption": "legenda opcional",
    "draws an image in the terminal": "desenha uma imagem no terminal",
    "path of the image": "caminho da imagem",
    "width in cells": "largura em células",
    "prints incoming messages": "imprime as mensagens que chegam",
    "seconds between fetches": "segundos entre buscas",
    "fetches once and exits": "busca uma vez e sai",
    "shows attachments but does not download them": "mostra os anexos mas não baixa",
    "network and swarm diagnostics": "diagnóstico da rede e das swarms",
    "also shows this Session ID's swarm": "mostra também a swarm desse Session ID",
    "rebuilds the node list": "refaz a lista de nós",
    "erases everything after a time without access": "apaga tudo depois de um tempo sem acesso",
    "on: turn on (with --after/--unit/...), off: turn off, status: show, install/uninstall: automatic hourly check, check: run the check now": "on: liga (com --after/--unit/...), off: desliga, status: mostra, install/uninstall: verificação automática de hora em hora, check: verifica agora",
    "how many units without access": "quantas unidades sem acesso",
    "hours, days, months or years": "horas, dias, meses ou anos",
    "notify your contacts before erasing": "avisar seus contatos antes de apagar",
    "create a new account after erasing": "criar uma conta nova depois de apagar",
    "install the automatic hourly check (default: yes)": "instalar a verificação automática de hora em hora (padrão: sim)",
    "interface language: en or pt": "idioma da interface: en ou pt",
    "protocol tests": "testes do protocolo",
    "includes a real round trip": "inclui uma ida e volta real",
    # --- TUI: atalhos e status ----------------------------------------------
    "close": "fechar",
    "cancel": "cancelar",
    "fetch now": "buscar agora",
    "clear screen": "limpar tela",
    "paste image": "colar imagem",
    "download attachment": "baixar anexo",
    "contact card": "cartão do contato",
    "my profile": "meu perfil",
    "help": "ajuda",
    "quit": "sair",
    "starting...": "iniciando...",
    "message, /help, or drag a file here": "mensagem, /ajuda, ou arraste um arquivo aqui",
    "nobody": "ninguém",
    "me: {sid}": "eu: {sid}",
    "name: {name}": "nome: {name}",
    "with: {who}": "com: {who}",
    "network ok": "rede ok",
    "connecting...": "conectando...",
    "network error": "rede com erro",
    "attachments: {n} (ctrl+b)": "anexos: {n} (ctrl+b)",
    "log: {n} (/log)": "log: {n} (/log)",
    "your profile (f3) -- {name}": "seu perfil (f3) -- {name}",
    # --- TUI: janelas -------------------------------------------------------
    "help -- arrows/PgUp/PgDn scroll, esc closes": "ajuda -- setas/PgUp/PgDn rolam, esc fecha",
    "Close": "Fechar",
    "Cancel": "Cancelar",
    "Open": "Abrir",
    "Message": "Mensagem",
    "Copy": "Copiar",
    "Save": "Salvar",
    "Remove": "Remover",
    "Continue": "Continuar",
    "Protect": "Proteger",
    "Remove password": "Tirar senha",
    "Show phrase": "Ver frase",
    "Hide phrase": "Esconder frase",
    "Kill switch": "Kill switch",
    "Erase everything": "Apagar tudo",
    "password": "senha",
    "repeat the password": "repita a senha",
    "type a password": "digite uma senha",
    "the two passwords do not match": "as duas senhas não batem",
    "use at least 8 characters": "use pelo menos 8 caracteres",
    "contact": "contato",
    "account ID": "ID da conta",
    "nickname (only for you)": "apelido (só para você)",
    "Session ID copied": "Session ID copiado",
    "my account": "minha conta",
    "password-protected": "protegida por senha",
    "NO password on disk": "SEM senha no disco",
    "display name (sent along with your messages)": "nome de exibição (vai junto das suas mensagens)",
    "whoever has these words controls the account:": "quem tiver estas palavras controla a conta:",
    "whoever has these words controls your account:": "quem tiver estas palavras controla sua conta:",
    "kill switch": "kill switch",
    "enabled": "ligado",
    "erase after": "apagar depois de",
    "without access": "sem acesso",
    "notify my contacts before erasing": "avisar meus contatos antes de apagar",
    "automatic check every hour, even with the app closed": "verificar de hora em hora, mesmo com o app fechado",
    "last access: {when}": "último acesso: {when}",
    "erases at: {when} (in {time})": "apaga em: {when} (daqui a {time})",
    "this account is password-protected: when the kill switch fires, the key that signs the notice is locked, so contacts will NOT be notified": "esta conta é protegida por senha: quando o kill switch disparar, a chave que assina o aviso estará trancada, então os contatos NÃO serão avisados",
    "ERASE EVERYTHING AND START OVER": "APAGAR TUDO E COMEÇAR DE NOVO",
    "This erases, with no way back:\n  - the current account (private key and recovery phrase)\n  - the whole conversation history\n  - downloaded and sent attachments\n  - the list of {n} conversation(s)\n\nThen a new account is created, with another Session ID.\nWhoever writes to the old ID no longer reaches you.": "Isto apaga, sem volta:\n  - a conta atual (chave privada e frase de recuperação)\n  - todo o histórico de conversas\n  - os anexos baixados e os enviados\n  - a lista de {n} conversa(s)\n\nDepois uma conta nova é criada, com outro Session ID.\nQuem te escrever no ID antigo não chega mais em você.",
    "notify my {n} contacts of the new ID before erasing": "avisar meus {n} contatos do ID novo antes de apagar",
    "type {word} to confirm": "digite {word} para confirmar",
    "Confirmation 2 of 2: type {word} to erase for good.": "Confirmação 2 de 2: digite {word} para apagar de vez.",
    "type exactly {word}": "escreva exatamente {word}",
    # --- TUI: conta e senha -------------------------------------------------
    "protected account": "conta protegida",
    "without the password this account cannot be opened (/quit to close)": "sem a senha não dá para abrir esta conta (/sair para fechar)",
    "\nthis account is encrypted on disk:\n  {sid}\n\ntype the password to open it.": "\nesta conta está cifrada no disco:\n  {sid}\n\ndigite a senha para abrir.",
    "wrong password.": "senha incorreta.",
    "could not open the profile: {error}": "falha ao abrir o perfil: {error}",
    "your Session account": "sua conta Session",
    "SAVE THE RECOVERY PHRASE -- it is the only way to recover the account:": "GUARDE A FRASE DE RECUPERAÇÃO -- é a única forma de recuperar a conta:",
    "(also stored in {path})": "(também fica em {path})",
    "/phrase shows your recovery phrase, /help lists the commands": "/frase mostra sua frase de recuperação, /ajuda lista os comandos",
    "initial destination ignored: {error}": "destino inicial ignorado: {error}",
    "account not loaded yet": "conta ainda não carregada",
    "wrong password -- the protection stays on": "senha incorreta -- a proteção continua ligada",
    "protection removed: the seed is in clear text again in account.json": "proteção removida: o seed voltou a ficar em claro em account.json",
    "remove the password": "tirar a senha",
    "type the current password.\n\nwithout it, whoever can read the account.json file gets your whole account.": "digite a senha atual.\n\nsem ela, quem tiver acesso ao arquivo account.json passa a ter a sua conta inteira.",
    "could not protect it: {error}": "não deu para proteger: {error}",
    "account protected: the seed is now encrypted with Argon2id + XChaCha20": "conta protegida: o seed agora fica cifrado com Argon2id + XChaCha20",
    "the password will be asked every time the interface opens": "a senha será pedida toda vez que a interface abrir",
    "the password cannot be recovered -- if you forget it, only the phrase saves the account": "não dá para recuperar a senha -- se esquecer, só a frase salva a conta",
    "note: with a password, the kill switch can no longer notify your contacts": "obs.: com senha, o kill switch não consegue mais avisar seus contatos",
    "protect the account": "proteger a conta",
    "choose a password (at least 8 characters).\n\nit encrypts the seed on disk with Argon2id + XChaCha20-Poly1305.\nthe password cannot be recovered: keep the recovery phrase too.": "escolha uma senha (mínimo 8 caracteres).\n\nela cifra o seed no disco com Argon2id + XChaCha20-Poly1305.\nnão há como recuperar a senha: guarde também a frase de recuperação.",
    "your display name: {name}": "seu nome de exibição: {name}",
    "this account is not password-protected": "esta conta não está protegida por senha",
    # --- TUI: kill switch e idioma ------------------------------------------
    "KILL SWITCH FIRED on {when}": "KILL SWITCH DISPAROU em {when}",
    "erased: {files}": "apagado: {files}",
    "contacts NOT notified: {reason}": "contatos NÃO avisados: {reason}",
    "notice sent to {ok} of {n} contact(s) ({failed} failed)": "aviso entregue a {ok} de {n} contato(s) ({failed} falharam)",
    "kill switch on: erases after {time} without access": "kill switch ligado: apaga depois de {time} sem acesso",
    "kill switch off": "kill switch desligado",
    "automatic check installed: {how}": "verificação automática instalada: {how}",
    "could not install the automatic check: {error}": "não deu para instalar a verificação automática: {error}",
    "automatic check removed": "verificação automática removida",
    "unknown language: use en or pt": "idioma desconhecido: use en ou pt",
    "language: {name} -- menus and shortcuts change the next time you open the app": "idioma: {name} -- menus e atalhos mudam na próxima vez que você abrir o app",
    "language: {name} -- /lang en or /lang pt": "idioma: {name} -- /idioma en ou /idioma pt",
    # --- TUI: conversa ------------------------------------------------------
    "conversation with ": "conversa com ",
    "f2 or right click on the list = contact card": "f2 ou botão direito na lista = cartão do contato",
    "(no messages yet)": "(sem mensagens ainda)",
    "no conversation open -- /to <session_id> starts one": "nenhuma conversa aberta -- /para <session_id> começa uma",
    "[attachment] {name}": "[anexo] {name}",
    " (new conversation)": " (nova conversa)",
    "open a conversation first: /to <session_id>": "abra uma conversa primeiro: /para <session_id>",
    "open a conversation first": "abra uma conversa primeiro",
    "start a conversation with /to <session_id>": "comece uma conversa com /para <session_id>",
    "usage: /to <session_id>": "uso: /para <session_id>",
    "{sid} added to the list": "{sid} entrou na lista",
    "conversation removed: {sid}": "conversa removida: {sid}",
    "that conversation is not in the list": "essa conversa não está na lista",
    "nickname of {sid}: {name}": "apelido de {sid}: {name}",
    "typing notice sent": "aviso de digitação enviado",
    "unknown command: /{cmd} (try /help)": "comando desconhecido: /{cmd} (tente /ajuda)",
    # --- TUI: rede ----------------------------------------------------------
    "network unavailable: {error}": "rede indisponível: {error}",
    "{n} service nodes, swarm with {m} nodes": "{n} service nodes, swarm com {m} nós",
    "fetch failed: {error}": "busca falhou: {error}",
    "could not fetch: {error}": "falha ao buscar: {error}",
    "unexpected error while fetching: {error}": "erro inesperado ao buscar: {error}",
    "no new messages": "nenhuma mensagem nova",
    "control message from {sid} ({kind})": "mensagem de controle de {sid} ({kind})",
    "the network is not ready yet": "a rede ainda não está pronta",
    "known service nodes: {n}": "service nodes conhecidos: {n}",
    "network clock: {ms} ms": "relógio da rede: {ms} ms",
    "my swarm: {n} nodes -- {nodes}": "minha swarm: {n} nós -- {nodes}",
    "destination swarm: {n} nodes -- {nodes}": "swarm do destino: {n} nós -- {nodes}",
    "could not query the network: {error}": "falha ao consultar a rede: {error}",
    "usage: /onion on | /onion off": "uso: /onion on | /onion off",
    "onion routing on (slower, hides your IP from the snodes)": "onion routing ligado (mais lento, esconde seu IP dos snodes)",
    "onion routing off (direct connection to the snodes)": "onion routing desligado (conexão direta aos snodes)",
    "stored log discarded": "relato guardado descartado",
    "nothing stored": "nada guardado",
    "network log on ({n} lines stored)": "relato da rede ligado ({n} linhas guardadas)",
    "network log hidden (/log turns it back on)": "relato da rede escondido (/log liga de volta)",
    # --- TUI: envio ---------------------------------------------------------
    "ok: sent {ok}/{n}": "ok: enviado {ok}/{n}",
    "ok: attachment sent {ok}/{n} ({kb} KB)": "ok: anexo enviado {ok}/{n} ({kb} KB)",
    "not sent: {error}": "não enviou: {error}",
    "the file was not sent: {error}": "não enviou o arquivo: {error}",
    "typing notice failed: {error}": "aviso de digitação falhou: {error}",
    "migration notice: {ok} delivered, {failed} failed": "aviso de migração: {ok} entregue(s), {failed} falha(s)",
    # --- TUI: anexos e imagens ----------------------------------------------
    "download it? ctrl+b or /download{n}   (/auto on stops asking)": "quer baixar? ctrl+b ou /baixar{n}   (/auto on não pergunta)",
    "{name}: could not download": "{name}: não deu para baixar",
    "saved in {path}  (/open shows it in the system)": "salvo em {path}  (/abrir mostra no sistema)",
    "file saved in {path}  (/open to open it)": "arquivo salvo em {path}  (/abrir para abrir)",
    "no attachment waiting for download": "nenhum anexo esperando download",
    "usage: /download [1 to {n}]": "uso: /baixar [1 a {n}]",
    "downloading {what}...": "baixando {what}...",
    "download failed: {error}": "falha ao baixar: {error}",
    "nothing to open yet": "nada para abrir ainda",
    "opening {name}": "abrindo {name}",
    "could not open it: {error}": "não consegui abrir: {error}",
    "could not show the image: {error}": "não deu para mostrar a imagem: {error}",
    "failed to draw the image ({kind}: {error})": "falha ao desenhar a imagem ({kind}: {error})",
    "usage: /file <path> [caption]": "uso: /arquivo <caminho> [legenda]",
    "unclosed quotes in the path": "aspas sem fechamento no caminho",
    "usage: /view <path of an image>": "uso: /ver <caminho de uma imagem>",
    "usage: /auto on | /auto off": "uso: /auto on | /auto off",
    "attachments will be downloaded automatically": "anexos serão baixados automaticamente",
    "I will ask before downloading attachments": "vou perguntar antes de baixar anexos",
    "now: {mode}, width {width}": "agora: {mode}, largura {width}",
    "modes: {modes}": "modos: {modes}",
    "the '{mode}' mode must probe the terminal before the interface opens -- close it and run: session-tui tui --mode {mode}": "o modo '{mode}' precisa sondar o terminal antes de a interface abrir -- feche e rode: session-tui tui --mode {mode}",
    "images will be drawn in '{mode}' mode": "imagens serão desenhadas no modo '{mode}'",
    "image width: {n} cells": "largura das imagens: {n} células",
    "usage: /width <8 to 200>": "uso: /largura <8 a 200>",
    # --- TUI: apagar tudo ---------------------------------------------------
    "nothing was erased": "nada foi apagado",
    "erasing everything and creating a new account...": "apagando tudo e criando conta nova...",
    "new account created": "conta nova criada",
    # --- imagens (imgview) --------------------------------------------------
    "file not found: {path}": "arquivo não encontrado: {path}",
    "not a readable image: {error}": "não é uma imagem legível: {error}",
    "the '{mode}' mode must probe the terminal before the interface opens; reopen with --mode {mode}": "o modo '{mode}' precisa sondar o terminal antes de a interface abrir; reabra com --mode {mode}",
    "failed to render: {error}": "falha ao renderizar: {error}",
    "failed to draw: {error}": "falha ao desenhar: {error}",
    "install Pillow to paste images": "instale o Pillow para colar imagens",
    "could not read the clipboard: {error}": "não foi possível ler a área de transferência: {error}",
    "there is no image in the clipboard": "não há imagem na área de transferência",
    "the copied files are not images": "os arquivos copiados não são imagens",
    "failed to save the pasted image: {error}": "falha ao salvar a imagem colada: {error}",
    # --- anexos (attachments) -----------------------------------------------
    "file too large: {n} B (limit {max})": "arquivo grande demais: {n} B (limite {max})",
    "the attachment key must have {n} bytes (it has {m})": "a chave do anexo deve ter {n} bytes (tem {m})",
    "attachment too short": "anexo curto demais",
    "attachment HMAC does not match": "HMAC do anexo não confere",
    "attachment digest does not match": "digest do anexo não confere",
    "invalid AES padding: {error}": "padding AES inválido: {error}",
    "the stream key must have {n} bytes (it has {m})": "a chave do stream deve ter {n} bytes (tem {m})",
    "attachment too short for the new format": "anexo curto demais para o formato novo",
    "unknown encryption type: {kind}": "tipo de criptografia desconhecido: {kind}",
    "invalid key or corrupted data: {error}": "chave inválida ou dados corrompidos: {error}",
    "the stream ended without the final tag": "o stream terminou sem a marca de fim",
    "invalid attachment padding": "padding do anexo inválido",
    "onion via {node}: HTTP {code}": "onion via {node}: HTTP {code}",
    "file server answered {code} via onion; trying direct": "file server respondeu {code} via onion; tentando direto",
    "upload via onion failed ({error}); trying direct": "upload via onion falhou ({error}); tentando direto",
    "upload failed: {error}": "upload falhou: {error}",
    "unexpected file server response: {body}": "resposta inesperada do file server: {body}",
    "invalid attachment url: {url}": "url de anexo inválida: {url}",
    "download via onion returned {code}; trying direct": "download via onion devolveu {code}; tentando direto",
    "download via onion failed ({error}); trying direct": "download via onion falhou ({error}); tentando direto",
    # --- cliente ------------------------------------------------------------
    "empty file": "arquivo vazio",
    "attachment without a key (cannot decrypt); skipping": "anexo sem chave (não dá para decifrar); ignorando",
    "attachment too large ({n} B); skipping": "anexo grande demais ({n} B); ignorando",
    "no account at {path} -- create one with `new`": "nenhuma conta em {path} -- crie uma com `new`",
    "could not sync the clock: {error}": "não foi possível sincronizar o relógio: {error}",
    "attachment not downloaded: {error}": "anexo não baixado: {error}",
    "ignoring message {hash}: {error}": "ignorando mensagem {hash}: {error}",
    "could not save the attachment: {error}": "não foi possível salvar o anexo: {error}",
    # --- cofre e perfil -----------------------------------------------------
    "empty password": "senha vazia",
    "this file is not protected": "este arquivo não está protegido",
    "the account is password-protected": "a conta está protegida por senha",
    "could not derive the key: {error}": "não foi possível derivar a chave: {error}",
    "the protected account file is corrupted": "o arquivo da conta protegida está corrompido",
    "wrong password": "senha incorreta",
    "the decrypted content is invalid": "o conteúdo decifrado é inválido",
    "account not found at {path}": "conta não encontrada em {path}",
    "invalid account at {path}": "conta inválida em {path}",
    # --- chaves e frase -----------------------------------------------------
    "a Session ID has 66 characters (this one has {n})": "um Session ID tem 66 caracteres (este tem {n})",
    "a Session ID starts with 05 (this one starts with {prefix})": "um Session ID começa com 05 (este começa com {prefix})",
    "prefix {prefix} is not a 1-to-1 account (groups/blinded community IDs are not supported here)": "o prefixo {prefix} não é de uma conta 1-para-1 (grupos/IDs blinded de community não são suportados aqui)",
    "the Session ID is not hexadecimal": "o Session ID não é hexadecimal",
    "the seed must have {a} or {b} bytes": "o seed deve ter {a} ou {b} bytes",
    "invalid length: {n}": "tamanho inválido: {n}",
    "the seed must be a multiple of 4 bytes": "o seed precisa ser múltiplo de 4 bytes",
    "too few words (13 expected)": "poucas palavras (esperadas 13)",
    "too many words (13 expected)": "palavras demais (esperadas 13)",
    "invalid number of words": "número de palavras inválido",
    "the last word (checksum) is missing": "falta a última palavra (checksum)",
    "invalid checksum: check the last word": "checksum inválido: confira a última palavra",
    "invalid wordlist: 1626 words expected": "wordlist inválida: esperadas 1626 palavras",
    "failed to decode the phrase": "falha ao decodificar a frase",
    "wordlist not found at {path}": "wordlist não encontrada em {path}",
    "unknown word near {word}": "palavra desconhecida perto de {word}",
    # --- protocolo (onion, wire, proto) -------------------------------------
    "response too short to contain nonce + tag": "resposta curta demais para conter nonce + tag",
    "v4 response is not a bencode list": "resposta v4 não é uma lista bencode",
    "empty path": "caminho vazio",
    "failed to decrypt the response: {error}": "falha ao decifrar a resposta: {error}",
    "malformed v4 response": "resposta v4 malformada",
    "empty v4 response": "resposta v4 vazia",
    "destination answered HTTP {code}: {body}": "destino respondeu HTTP {code}: {body}",
    "invalid length in v4 response": "tamanho inválido na resposta v4",
    "v4 header is not JSON": "cabeçalho v4 não é JSON",
    "decrypted response is not JSON": "resposta decifrada não é JSON",
    "truncated varint": "varint truncado",
    "varint too long": "varint longo demais",
    "truncated length-delimited field": "campo delimitado truncado",
    "unknown wire type: {wire}": "wire type desconhecido: {wire}",
    "payload is neither a WebSocketMessage nor an Envelope": "payload não é WebSocketMessage nem Envelope",
    "decrypted message too short": "mensagem decifrada curta demais",
    "invalid sender signature": "assinatura do remetente inválida",
    "envelope type {type} not supported (1-to-1 only)": "envelope tipo {type} não suportado (só 1-para-1)",
    "envelope without content": "envelope sem conteúdo",
    "WebSocketMessage without a body": "WebSocketMessage sem corpo",
    "stopped typing": "parou de digitar",
    "is typing...": "digitando...",
    # --- rede (snode) -------------------------------------------------------
    "did not respond": "não respondeu",
    "took too long": "demorou demais",
    "TLS error": "erro de TLS",
    "connection refused": "conexão recusada",
    "no seed node answered -- {errors}": "nenhum seed node respondeu -- {errors}",
    "{method} failed on {n} nodes: {last}": "{method} falhou em {n} nós: {last}",
    "{method} failed on {n} swarm nodes: {last}": "{method} falhou em {n} nós da swarm: {last}",
    "node list updated: {n} snodes": "lista de nós atualizada: {n} snodes",
    "{seed}: empty list": "{seed}: lista vazia",
    "no snodes available": "sem snodes disponíveis",
    "not enough snodes to build an onion path": "snodes insuficientes para montar um caminho onion",
    "onion via {node}: HTTP {code} {text}": "onion via {node}: HTTP {code} {text}",
    "{node}: the swarm changed": "{node}: a swarm mudou",
    "empty swarm for {sid}...": "swarm vazia para {sid}...",
    "message too large: {n} > {max} bytes": "mensagem grande demais: {n} > {max} bytes",
    "no swarm node accepted the message: {reasons}": "nenhum nó da swarm aceitou a mensagem: {reasons}",
    "could not update the node list; using the cache": "falha ao atualizar a lista de nós; usando o cache",
    "onion via {node}: {reason}": "onion via {node}: {reason}",
    "local clock corrected by {ms} ms": "relógio local corrigido em {ms} ms",
    "{node}: non-JSON response": "{node}: resposta não-JSON",
    "the swarm of {sid}... changed, refreshing": "a swarm de {sid}... mudou, atualizando",
    # --- sistema: Windows ---------------------------------------------------
    "Windows Task Scheduler, task '{name}', every hour": "Agendador de Tarefas do Windows, tarefa '{name}', de hora em hora",
    "could not create the scheduled task: {error}": "não deu para criar a tarefa agendada: {error}",
    # --- sistema: Linux -----------------------------------------------------
    "install wl-clipboard (Wayland) or xclip (X11) to paste images -- {error}": "instale wl-clipboard (Wayland) ou xclip (X11) para colar imagens -- {error}",
    "xdg-open not found: install xdg-utils to open files": "xdg-open não encontrado: instale o xdg-utils para abrir arquivos",
    "systemd user timer '{name}', every hour (to run while you are logged out: loginctl enable-linger)": "timer de usuário do systemd '{name}', de hora em hora (para rodar com você deslogado: loginctl enable-linger)",
    "crontab entry '{name}', every hour": "entrada no crontab '{name}', de hora em hora",
    "could not create the systemd timer: {error}": "não deu para criar o timer do systemd: {error}",
    "could not update the crontab: {error}": "não deu para atualizar o crontab: {error}",
    "no systemd user session or crontab found; add this to your scheduler to run every hour: {cmd}": "nem sessão de usuário do systemd nem crontab encontrados; agende isto para rodar de hora em hora: {cmd}",
}


LONGOS_PT = {
    "help": """IMAGENS E ARQUIVOS   (qualquer tipo, até 10 MB)

  /img <caminho> [legenda]   envia uma imagem ou arquivo
                             aliases: /arquivo, /anexo
  arrastar para a janela     solta o caminho na linha; enter envia
  ctrl+v  (ou ctrl+g, /colar)  envia a imagem que está copiada
  /baixar [n]  ou ctrl+b     baixa o anexo que chegou e desenha aqui
  /auto on|off               baixar sem perguntar (padrão: off, pergunta)
  /abrir [caminho]           abre o baixado no programa padrão do sistema
  /ver <caminho>             desenha uma imagem no painel
  /modo                      explica os modos de desenho
  /modo meio|blocos          troca o modo (sixel/tgp: abra com --mode sixel)
  /largura <células>         tamanho do desenho (padrão 44)

CONVERSAS

  /para <session_id>         abre (ou cria) a conversa -- alias /to
  /add <session_id>          só adiciona à lista, sem trocar de tela
  /perfil [id]  ou f2        cartão do contato: ID completo, apelido, copiar
                             (botão direito na lista faz o mesmo)
  /apelido <apelido>         apelido da conversa atual (alias /nick)
  /rm [id]                   remove a conversa da lista
  /digitando                 manda o aviso de "digitando..."

MINHA CONTA

  /eu  ou f3  ou o avatar no canto superior esquerdo
                             nome, Session ID, frase, senha, kill switch
  /nome <nome>               nome de exibição (vai junto das mensagens)
  /frase                     mostra a frase de recuperação (cuidado!)
  /proteger                  cifra o seed no disco com uma senha
                             (Argon2id + XChaCha20-Poly1305)
  /desproteger               tira a senha (volta a ficar em claro)
  /killswitch                apaga tudo depois de um tempo sem acesso
  /idioma en|pt              idioma da interface (English / Português)
  /removeall                 APAGA tudo e começa uma conta nova; pede
                             confirmação dupla e pode avisar seus contatos

REDE E TELA

  /poll  ou ctrl+r           busca mensagens agora
  /rede                      nós conhecidos, swarm e relógio da rede
  /onion on|off              roteamento em 3 saltos (esconde seu IP)
  /log [n|limpar]            mostra/esconde o relato da rede (padrão: escondido)
  /limpar  ou ctrl+l         limpa o painel da conversa
  /ajuda  ou f1              esta janela
  /sair  ou ctrl+c           fecha

Qualquer outra linha vira mensagem para a conversa aberta.""",
    "image_modes": """como as imagens são desenhadas:

  half    (padrão, alias 'meio') dois pixels por célula: a metade de cima vira
          a cor da letra e a de baixo a cor do fundo, no caractere de meio
          bloco. É o que dá mais detalhe usando só cor ANSI -- funciona em
          qualquer terminal, cmd.exe incluído, e nunca escreve nada por fora
          do Textual.

  blocks  (alias 'blocos') um pixel por célula, usando o bloco cheio colorido.
          Metade da resolução vertical do 'half', mas só usa cor de letra:
          serve para terminais que pintam mal o fundo ou deixam linha entre
          as células.

  sixel   imagem de verdade, em pixels, via protocolo Sixel. Precisa de
          Windows Terminal 1.22+, WezTerm, foot, mlterm ou xterm com sixel.
  tgp     imagem de verdade pelo protocolo gráfico do Kitty (Kitty, Ghostty).
  auto    testa o terminal e escolhe sozinho entre tgp, sixel e half.

Os três últimos precisam sondar o terminal (escrever uma pergunta na tela e
ler a resposta do teclado) e isso só é seguro ANTES da interface abrir -- por
isso são escolhidos na linha de comando:  session-tui tui --mode sixel""",
    "killswitch": (
        "Se ninguém usar esta conta pelo tempo abaixo, tudo é apagado: "
        "chave, frase de recuperação, histórico, anexos e contatos.\n\n"
        "Verificado sempre que o app abre e, com a verificação automática, "
        "de hora em hora mesmo com o app fechado. Abrir o app conta como acesso."
    ),
}
