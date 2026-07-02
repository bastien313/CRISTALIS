# -*- coding: utf-8 -*-
"""
Réseau LAN pour CRISTALIS.

- Peer : connexion TCP, messages JSON délimités par des sauts de ligne.
- HostListener : attente d'un client TCP + réponse aux requêtes de
  découverte UDP diffusées sur le réseau local.
- Discovery : côté client, diffusion périodique d'une requête de
  découverte et collecte des hôtes qui répondent.
"""

import json
import queue
import socket
import threading
import time

TCP_PORT = 45455
DISCO_PORT = 45454
DISCO_PING = b"CRISTALIS_DISCOVER_V1"
DISCO_PONG = b"CRISTALIS_HOST_V1"


class Peer:
    """Connexion TCP full-duplex ; la réception tourne dans un thread."""

    def __init__(self, sock):
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        self.inbox = queue.Queue()
        self.alive = True
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
                try:
                    self.inbox.put(json.loads(line.decode()))
                except ValueError:
                    pass
        except OSError:
            pass
        self.alive = False

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
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


def connect(ip, timeout=3.0):
    return Peer(socket.create_connection((ip, TCP_PORT), timeout=timeout))


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
