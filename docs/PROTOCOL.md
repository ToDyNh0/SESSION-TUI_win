# How Session TUI speaks the Session protocol

This client is written from scratch in Python. It does not embed or call the official app or
`libsession-util`; instead it reimplements, byte for byte, the parts of the protocol needed for
1-to-1 conversations. The formats below were checked line by line against the official sources —
`src/session_protocol.cpp`, `src/session_encrypt.cpp`, `src/onionreq/builder.cpp` and `proto/*.proto`
from libsession-util, plus `ts/util/accountManager.ts` and `ts/session/crypto/mnemonic.ts` from
session-desktop — and tested against the live network.

- [1. Identity](#1-identity)
- [2. Finding the network](#2-finding-the-network)
- [3. Swarms, store and retrieve](#3-swarms-store-and-retrieve)
- [4. Message format](#4-message-format)
- [5. Onion requests](#5-onion-requests)
- [6. Attachments](#6-attachments)
- [7. Local storage and the kill switch](#7-local-storage-and-the-kill-switch)

## 1. Identity

`session_native/keys.py`, `session_native/mnemonic.py`

```text
seed (16 random bytes)
  -> zero-padded to 32 bytes
  -> crypto_sign_seed_keypair()             Ed25519 (signatures)
  -> crypto_sign_ed25519_pk_to_curve25519() X25519  (encryption)

Session ID = "05" + hex(X25519 public key)      66 characters
```

The **recovery phrase** is the Monero-style mnemonic the official app uses: the 16-byte seed is
split into four 4-byte words, each encoded as three words from a 1,626-word list, plus a 13th
checksum word chosen with CRC-32 over the 3-letter prefixes. Only the first three letters of each
word matter when decoding.

## 2. Finding the network

`session_native/snode.py`

1. `POST https://seed{1,2,3}.getsession.org:4432/json_rpc` with `get_n_service_nodes` returns the
   active service nodes (about 1,200) with IP, storage port and Ed25519/X25519 keys. The list is
   cached in `snodes.json` for 2 hours.
2. Every storage RPC is `POST https://<ip>:<port>/storage_rpc/v1` with `{"method", "params"}`.
3. `info` returns the network time; the client keeps the offset, because signed requests are only
   accepted within ±60 s.
4. A node that fails (timeout, TLS, refused) is put in quarantine for 10 minutes, so the client stops
   retrying a dead node.

Service node TLS certificates are self-signed; their real identity is the key published on the
network, which is what onion requests encrypt to.

## 3. Swarms, store and retrieve

- `get_swarm(pubkey)` → the group of nodes that stores messages for a Session ID. A `421` answer
  means the swarm changed; the client refreshes it and retries.
- `store` → deposits a message in the **recipient's** swarm, namespace 0, TTL 14 days. Namespace 0
  accepts unauthenticated writes: anyone can write to anyone's inbox, only the owner can read it.
- `retrieve` → reads your own swarm. It requires an Ed25519 signature over
  `"retrieve" || timestamp` and uses `last_hash` to fetch only new messages.
- The node returns the message hash `blake2b(pubkey || namespace || data)`; the client computes it
  locally to confirm the node stored exactly the bytes it sent.

## 4. Message format

`session_native/wire.py`, `session_native/proto.py`

```text
Content (protobuf: DataMessage{body, attachments, timestamp, profile{displayName}}, sigTimestamp)
  -> padding to a multiple of 160 bytes, 0x80 terminator
  -> plaintext || sender Ed25519 pubkey || Ed25519 signature
       signature over (plaintext || sender Ed25519 pubkey || recipient X25519 pubkey)
  -> crypto_box_seal() to the recipient's X25519 key        (anonymous sealed box)
  -> Envelope{type=SESSION_MESSAGE(6), timestamp, content, proSig}
  -> WebSocketMessage{type=REQUEST, request{body=Envelope}}
  -> base64 -> the `data` field of `store`
```

- The sender's identity travels **inside** the sealed box; the network never sees who sent it.
  The recipient opens the box, verifies the signature and derives the sender's Session ID from the
  embedded Ed25519 key.
- `proSig` is always filled — with a signature from a throwaway key — exactly like current clients,
  so messages from Session Pro and non-Pro users look the same on the wire.
- Typing notices are a `TypingMessage` with a 20-second TTL.
- There is no compiled protobuf: `proto.py` writes and reads the wire format directly, using the
  field numbers from `SessionProtos.proto`.

## 5. Onion requests

`session_native/onion.py`

```text
you -> hop 1 -> hop 2 -> hop 3 -> destination (service node, or the file server)
```

- Every layer is encrypted with XChaCha20-Poly1305 using a fresh ephemeral X25519 key; the layer key
  is `blake2b-32(X25519(ephemeral_sk, node_pk) || ephemeral_pk || node_pk)`.
- Layer format: `[size: 4 bytes LE][encrypted blob][routing JSON]`. Each hop learns only who sent the
  layer and who to forward it to.
- Service node destinations use `POST /onion_req/v2`; the file server uses the v4 format
  (`/oxen/v4/lsrpc`, bencoded request and response), so uploads and downloads can also go over onion.

## 6. Attachments

`session_native/attachments.py`, `session_native/client.py`

**Sending** uses the classic format, accepted by every Session client, old and new:

```text
file -> padding to 1.05^n bytes (minimum 541)
     -> AES-256-CBC (PKCS7) with key[0:32] and a random IV
     -> blob = IV || ciphertext || HMAC-SHA256(key[32:64], IV || ciphertext)
     -> digest = SHA-256(blob)
     -> POST /file on the file server -> id -> https://filev2.getsession.org/file/<id>
```

The message carries an `AttachmentPointer` with the URL, the 64-byte key, the digest, the real size
(the padding is cut off on arrival), the file name and, for images, the dimensions.

**Receiving** supports both formats, chosen by key size:

| Key | Format | Sent by |
| --- | --- | --- |
| 64 bytes | classic: AES-256-CBC + HMAC-SHA256 + SHA-256 digest | this client, older apps |
| 32 bytes | `crypto_secretstream_xchacha20poly1305` in 32 KiB chunks, `#d` in the URL | current official apps |

Downloads are verified (HMAC and digest, or the stream's final tag), decrypted and saved under
`attachments/` with a sanitized name — the sender cannot choose the path.

## 7. Local storage and the kill switch

`session_native/profile.py`, `session_native/cofre.py`, `session_native/killswitch.py`

- `account.json` holds the seed. With a password it becomes
  `XChaCha20-Poly1305(Argon2id(password, salt, OPSLIMIT_MODERATE, MEMLIMIT_MODERATE), seed+phrase)`
  with a fresh salt and nonce on every write; the Session ID stays in clear text.
- `config.json` keeps the language, the kill switch settings and the last access time. It survives
  "erase everything" so the settings apply to the next account too.
- When the kill switch fires: if notifying is on and the key is available, every contact (the list
  plus everyone in the history) gets `I am moving my account to:<new id>` or
  `This account is no longer in use.` from the **old** account; then `account.json`, `state.json`,
  `history.jsonl`, `attachments/` and `enviados/` are overwritten with random bytes and deleted; then
  the optional new account is created and a line is appended to `killswitch.log`.
