# -*- coding: utf-8 -*-
"""
Réseau LAN et Internet pour CRISTALIS.

- Peer : connexion TCP, messages JSON délimités par des sauts de ligne.
- HostListener : attente d'un client TCP + réponse aux requêtes de
  découverte UDP diffusées sur le réseau local.
- Discovery : côté client, diffusion périodique d'une requête de
  découverte et collecte des hôtes qui répondent.
- relay_host / relay_join : parties Internet via le serveur relais
  (server/relay.py sur un VPS) et codes de partie — les deux joueurs se
  connectent en sortant, aucun port à ouvrir sur les box.
- host_handshake / join_handshake : échange hello/ready/go commun au LAN
  et à l'Internet ; l'hôte mesure le RTT et choisit un NET_DELAY adapté,
  envoyé au client (identique des deux côtés : lockstep préservé).

Ce module ne dépend que de la stdlib (pas de pygame, pas de data.py).
"""

import collections
import json
import math
import os
import socket
import threading
import time

TCP_PORT = 45455
DISCO_PORT = 45454
DISCO_PING = b"CRISTALIS_DISCOVER_V1"
DISCO_PONG = b"CRISTALIS_HOST_V1"

# Adresse du serveur relais Internet (« hôte » ou « hôte:port »). À pointer
# vers ton VPS (constante ou variable d'env CRISTALIS_RELAY) ; la valeur par
# défaut permet de tester avec `python server/relay.py` en local.
RELAY_PORT = 45456
RELAY_ADDR = os.environ.get("CRISTALIS_RELAY", "127.0.0.1")

# NET_DELAY adaptatif : bornes en ticks (à 20 Hz). 3 ticks = 150 ms de marge
# (le LAN d'origine) ; 12 ticks = 600 ms, au-delà le jeu serait injouable.
NET_DELAY_MIN = 3
NET_DELAY_MAX = 12


class Peer:
    """Connexion TCP full-duplex ; la réception tourne dans un thread."""

    def __init__(self, sock):
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        # deque plutôt que Queue : wait_msg doit pouvoir remettre en tête
        # les messages non consommés (appendleft) — append/popleft sont
        # atomiques, l'accès concurrent avec le thread de réception est sûr
        self.inbox = collections.deque()
        self.alive = True
        # horodatage de la dernière ligne reçue : sert au timeout applicatif
        # (une connexion Internet peut mourir en silence, TCP ne le signale
        # qu'au bout de plusieurs minutes)
        self.last_recv = time.monotonic()
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def send(self, obj):
        if not self.alive:
            return
        try:
            data = (json.dumps(obj, separators=(",", ":")) + "\n").encode()
            self.sock.sendall(data)
        except OSError:
            self.alive = False

    def _recv_loop(self):
        try:
            f = self.sock.makefile("rb")
            for line in f:
                self.last_recv = time.monotonic()
                try:
                    self.inbox.append(json.loads(line.decode()))
                except ValueError:
                    pass
        except OSError:
            pass
        self.alive = False

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.inbox.popleft())
            except IndexError:
                return out

    def close(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def local_ip():
    """Adresse IP locale « sortante » (aucun paquet n'est réellement émis)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def parse_addr(text, default_port=TCP_PORT):
    """Découpe « hôte » ou « hôte:port » en (hôte, port)."""
    host, _, port = text.strip().partition(":")
    return host, int(port) if port.isdigit() else default_port


def connect(ip, port=TCP_PORT, timeout=3.0):
    return Peer(socket.create_connection((ip, port), timeout=timeout))


# ---- handshake commun LAN / Internet

def wait_msg(peer, want, timeout=6.0):
    """Attend un message réseau dont le type est `want` (str ou tuple) ;
    renvoie le message ou None. Les messages antérieurs sont ignorés, ceux
    reçus APRÈS le message attendu sont remis en tête de la boîte (ex. les
    premiers "tick" qui suivent le "go" du handshake dans la même rafale)."""
    if isinstance(want, str):
        want = (want,)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout and peer.alive:
        batch = peer.poll()
        for i, msg in enumerate(batch):
            if msg.get("t") in want:
                for later in reversed(batch[i + 1:]):
                    peer.inbox.appendleft(later)
                return msg
        time.sleep(0.02)
    return None


def pick_net_delay(rtt, tick_dt=1 / 20):
    """Choisit le NET_DELAY (en ticks) couvrant le RTT mesuré, borné."""
    return max(NET_DELAY_MIN, min(NET_DELAY_MAX,
                                  int(math.ceil(rtt / tick_dt)) + 1))


def host_handshake(peer, seed, cfg, ver, timeout=6.0):
    """Côté hôte : envoie hello (seed + config), mesure le RTT sur la
    réponse ready, choisit le NET_DELAY et l'envoie dans go.
    Renvoie le net_delay, ou None si le client ne répond pas."""
    peer.send(dict(t="hello", seed=seed, pid=1, ver=list(ver), cfg=cfg))
    t0 = time.monotonic()
    if wait_msg(peer, "ready", timeout) is None:
        return None
    nd = pick_net_delay(time.monotonic() - t0)
    peer.send(dict(t="go", nd=nd))
    return nd


def join_handshake(peer, timeout=6.0):
    """Côté client : attend hello, répond ready, attend go.
    Renvoie (hello, net_delay) ou None si l'hôte ne répond pas."""
    hello = wait_msg(peer, "hello", timeout)
    if hello is None:
        return None
    peer.send(dict(t="ready"))
    go = wait_msg(peer, "go", timeout)
    if go is None:
        return None
    return hello, max(1, int(go.get("nd", NET_DELAY_MIN)))


# ---- parties Internet via le serveur relais (server/relay.py)

def relay_connect(addr=None, timeout=4.0):
    host, port = parse_addr(addr if addr is not None else RELAY_ADDR,
                            RELAY_PORT)
    return Peer(socket.create_connection((host, port), timeout=timeout))


def relay_host(addr=None):
    """Crée une partie sur le relais : renvoie (peer, code) ou (None, erreur).
    Le pair reçoit ensuite {"t": "paired"} quand un invité entre le code ;
    à partir de là le relais est un tuyau transparent."""
    try:
        peer = relay_connect(addr)
    except OSError:
        return None, "Relais injoignable (" + str(addr or RELAY_ADDR) + ")"
    peer.send(dict(t="host"))
    msg = wait_msg(peer, "code", 5.0)
    if msg is None:
        peer.close()
        return None, "Le relais ne répond pas."
    return peer, str(msg.get("code", ""))


def relay_join(code, addr=None):
    """Rejoint une partie par son code : renvoie (peer, "") ou (None, erreur)."""
    try:
        peer = relay_connect(addr)
    except OSError:
        return None, "Relais injoignable (" + str(addr or RELAY_ADDR) + ")"
    peer.send(dict(t="join", code=code))
    msg = wait_msg(peer, ("paired", "err"), 8.0)
    if msg is None:
        peer.close()
        return None, "Le relais ne répond pas."
    if msg["t"] == "err":
        peer.close()
        return None, str(msg.get("msg", "Code inconnu."))
    return peer, ""


class HostListener:
    """Côté hôte : accepte un client TCP et répond à la découverte UDP."""

    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("", TCP_PORT))
        self.srv.listen(1)
        self.srv.setblocking(False)
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.udp.bind(("", DISCO_PORT))
        except OSError:
            self.udp.close()
            self.udp = None
        if self.udp is not None:
            self.udp.setblocking(False)

    def poll(self):
        """À appeler à chaque frame ; renvoie un Peer dès qu'un client arrive."""
        if self.udp is not None:
            for _ in range(8):
                try:
                    data, addr = self.udp.recvfrom(64)
                except (BlockingIOError, OSError):
                    break
                if data == DISCO_PING:
                    try:
                        self.udp.sendto(DISCO_PONG, addr)
                    except OSError:
                        pass
        try:
            sock, _addr = self.srv.accept()
            return Peer(sock)
        except (BlockingIOError, OSError):
            return None

    def close(self):
        for s in (self.srv, self.udp):
            if s is not None:
                try:
                    s.close()
                except OSError:
                    pass


class Discovery:
    """Côté client : diffuse un ping et liste les hôtes qui répondent."""

    def __init__(self):
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.udp.setblocking(False)
        except OSError:
            self.udp.close()
            self.udp = None
        self.hosts = {}
        self.last_ping = 0.0

    def poll(self):
        if self.udp is None:
            return []
        now = time.monotonic()
        if now - self.last_ping > 1.0:
            self.last_ping = now
            try:
                self.udp.sendto(DISCO_PING, ("255.255.255.255", DISCO_PORT))
            except OSError:
                pass
        for _ in range(16):
            try:
                data, addr = self.udp.recvfrom(64)
            except (BlockingIOError, OSError):
                break
            if data == DISCO_PONG:
                self.hosts[addr[0]] = now
        return sorted(ip for ip, t in self.hosts.items() if now - t < 4.0)

    def close(self):
        if self.udp is not None:
            try:
                self.udp.close()
            except OSError:
                pass
