# -*- coding: utf-8 -*-
"""
CRISTALIS — serveur relais Internet (à faire tourner sur un VPS).

Principe : les deux joueurs se connectent en TCP *sortant* vers ce serveur
(aucun port à ouvrir sur leurs box). L'hôte envoie {"t": "host"} et reçoit
un code de partie court ({"t": "code", "code": "AZUR-7"}). L'invité envoie
{"t": "join", "code": ...} ; le serveur répond {"t": "paired"} aux deux et
fait suivre les octets dans les deux sens, sans regarder le contenu — le
lockstep du jeu ne voit qu'un tuyau. Protocole : JSON ligne par ligne,
comme netcode.Peer.

Lancer :  python relay.py [port]        (défaut : 45456)
Aucune dépendance hors stdlib. Sur le VPS : un service systemd suffit.
"""

import asyncio
import json
import random
import sys

RELAY_PORT = 45456
HANDSHAKE_TIMEOUT = 30.0   # s pour recevoir la première ligne
HOST_WAIT_TIMEOUT = 600.0  # s d'attente d'un invité avant expiration du code
# alphabet sans caractères ambigus (pas de I/L/O/0/1)
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

pending = {}  # code -> Future résolue avec (reader, writer, done_future)


def new_code(rng=random.SystemRandom()):
    while True:
        s = "".join(rng.choice(CODE_ALPHABET) for _ in range(5))
        code = s[:4] + "-" + s[4]
        if code not in pending:
            return code


def send(writer, obj):
    writer.write((json.dumps(obj, separators=(",", ":")) + "\n").encode())


async def pipe(reader, writer, prefix=b""):
    """Fait suivre les octets d'une connexion vers l'autre jusqu'à EOF."""
    try:
        if prefix:
            writer.write(prefix)
            await writer.drain()
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


async def handle_host(reader, writer):
    code = new_code()
    fut = asyncio.get_running_loop().create_future()
    pending[code] = fut
    send(writer, dict(t="code", code=code))
    await writer.drain()
    # on surveille en parallèle l'arrivée d'un invité et la socket de l'hôte
    # (s'il quitte l'écran d'attente, la lecture rend EOF et on libère le code)
    watch = asyncio.ensure_future(reader.read(4096))
    try:
        done, _ = await asyncio.wait({fut, watch}, timeout=HOST_WAIT_TIMEOUT,
                                     return_when=asyncio.FIRST_COMPLETED)
    finally:
        pending.pop(code, None)
    if fut not in done:  # hôte parti ou code expiré
        watch.cancel()
        if not fut.done():
            fut.cancel()
        writer.close()
        return
    g_reader, g_writer, g_done = fut.result()
    # octets déjà lus par la surveillance : à réinjecter vers l'invité
    early = watch.result() if watch in done else b""
    if not early and watch in done:  # EOF de l'hôte juste avant l'appariement
        g_writer.close()
        g_done.set_result(None)
        writer.close()
        return
    if not watch.done():
        # attendre la fin effective de l'annulation : un StreamReader
        # n'accepte qu'une lecture à la fois, la pompe va relire ce reader
        watch.cancel()
        try:
            await watch
        except (asyncio.CancelledError, ConnectionError, OSError):
            pass
    send(writer, dict(t="paired"))
    send(g_writer, dict(t="paired"))
    try:
        await asyncio.gather(pipe(reader, g_writer, prefix=early),
                             pipe(g_reader, writer))
    finally:
        if not g_done.done():
            g_done.set_result(None)


async def handle_join(reader, writer, code):
    fut = pending.get(code)
    if fut is None or fut.done():
        send(writer, dict(t="err", msg="Code inconnu ou expiré."))
        await writer.drain()
        writer.close()
        return
    done = asyncio.get_running_loop().create_future()
    fut.set_result((reader, writer, done))
    # le pompage est piloté par la coroutine de l'hôte ; on attend la fin
    await done


async def handle(reader, writer):
    try:
        line = await asyncio.wait_for(reader.readline(), HANDSHAKE_TIMEOUT)
        msg = json.loads(line.decode())
    except (asyncio.TimeoutError, ValueError, UnicodeDecodeError,
            ConnectionError, OSError):
        writer.close()
        return
    try:
        if msg.get("t") == "host":
            await handle_host(reader, writer)
        elif msg.get("t") == "join":
            await handle_join(reader, writer, str(msg.get("code", "")).upper())
        else:
            writer.close()
    except (ConnectionError, OSError, asyncio.CancelledError):
        try:
            writer.close()
        except OSError:
            pass


async def serve(port=RELAY_PORT, host="0.0.0.0"):
    server = await asyncio.start_server(handle, host, port)
    return server


async def main(port):
    server = await serve(port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"Relais CRISTALIS en écoute sur {addrs}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else RELAY_PORT
    try:
        asyncio.run(main(p))
    except KeyboardInterrupt:
        pass
