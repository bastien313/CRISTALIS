# -*- coding: utf-8 -*-
"""
CRISTALIS — écrans de menu : accueil, difficulté, options de partie
(joueurs/équipes, vitesse, zombies, taille de carte) et écrans réseau.
"""

import math
import random
import sys
import time

import pygame

import art
import netcode
from art import clamp
from data import (AUTOTEST, C_BAD, C_CRYSTAL, DEFAULT_CONFIG, DIFFICULTES,
                  MAP_SIZES, MAX_PLAYERS, SCREEN_H, SCREEN_W, SMOKE)


def global_key(e):
    """Touches globales, valables dans tous les écrans.
    F11 : bascule plein écran. Renvoie True si l'événement est consommé."""
    if e.type == pygame.KEYDOWN and e.key == pygame.K_F11 and not (AUTOTEST or SMOKE):
        pygame.display.toggle_fullscreen()
        return True
    return False


class MenuUI:
    """Décor, titre animé et boutons partagés par tous les écrans de menu."""

    def __init__(self):
        self.font_h = pygame.font.SysFont("georgia", 58, bold=True)
        self.font_b = pygame.font.SysFont("georgia", 21, bold=True)
        self.font = pygame.font.SysFont("segoeui", 16)
        self.font_s = pygame.font.SysFont("segoeui", 13)

        bg = pygame.Surface((SCREEN_W, SCREEN_H))
        art.vgrad(bg, (0, 0, SCREEN_W, SCREEN_H), (10, 12, 30), (40, 26, 56))
        rng = random.Random(3)
        for _ in range(140):
            x, y = rng.randint(0, SCREEN_W - 1), rng.randint(0, SCREEN_H // 2)
            b = rng.randint(90, 210)
            bg.set_at((x, y), (b, b, min(255, b + 40)))
        for i, (hh, col) in enumerate([(210, (22, 26, 44)), (150, (16, 20, 34)),
                                       (95, (12, 14, 26))]):
            pts = [(0, SCREEN_H)]
            for x in range(0, SCREEN_W + 40, 40):
                pts.append((x, SCREEN_H - hh + math.sin(x * 0.01 + i * 2) * 26
                            + rng.randint(-8, 8)))
            pts.append((SCREEN_W, SCREEN_H))
            pygame.draw.polygon(bg, col, pts)
        shards = [(rng.randint(40, SCREEN_W - 40), SCREEN_H - rng.randint(20, 130),
                   rng.uniform(6, 22)) for _ in range(26)]
        for x, y, sz in sorted(shards, key=lambda s: s[2]):
            g = art.glow((16, 44, 58), int(sz * 2.4))
            bg.blit(g, g.get_rect(center=(x, y - sz * 0.4)),
                    special_flags=pygame.BLEND_ADD)
            art.draw_shard(bg, x, y, sz * 0.5, sz, (96, 216, 255))
        bg.blit(art.vignette(SCREEN_W, SCREEN_H), (0, 0))
        self.bg = bg
        self.rng = rng
        self.motes = [[rng.uniform(0, SCREEN_W), rng.uniform(0, SCREEN_H),
                       rng.uniform(6, 26)] for _ in range(40)]
        self.t = 0.0

    def frame(self, screen, dt, subtitle, foot="Échap : retour"):
        self.t += dt
        t = self.t
        screen.blit(self.bg, (0, 0))
        for m in self.motes:
            m[1] -= m[2] * dt
            if m[1] < -8:
                m[0], m[1] = self.rng.uniform(0, SCREEN_W), SCREEN_H + 8
            g = art.glow((20, 60, 80), 4)
            screen.blit(g, g.get_rect(center=(m[0], m[1])),
                        special_flags=pygame.BLEND_ADD)
        # grand cristal central animé
        cx, cy = SCREEN_W / 2, 168
        pulse = 0.75 + 0.25 * math.sin(t * 2)
        g = art.glow((18, 54, 70), int(64 * pulse) + 20)
        screen.blit(g, g.get_rect(center=(cx, cy)), special_flags=pygame.BLEND_ADD)
        for i in range(5):
            a = t * 0.5 + i * math.tau / 5
            ox = math.cos(a) * 78
            oy = math.sin(a) * 16
            h = 30 + 10 * math.sin(t * 2 + i)
            art.draw_shard(screen, cx + ox, cy + oy, 11, h, (96, 216, 255))
        art.draw_shard(screen, cx, cy - 6, 16, 44 * pulse + 10, (140, 232, 255))

        title = self.font_h.render("C R I S T A L I S", True, (150, 232, 255))
        for off in (26, 14):
            gt = pygame.transform.smoothscale(
                title, (title.get_width() + off, title.get_height() + off // 2))
            screen.blit(gt, gt.get_rect(center=(SCREEN_W / 2, 262)),
                        special_flags=pygame.BLEND_ADD)
        screen.blit(title, title.get_rect(center=(SCREEN_W / 2, 262)))
        sub = self.font.render(subtitle, True, (168, 178, 196))
        screen.blit(sub, sub.get_rect(center=(SCREEN_W / 2, 306)))
        f = self.font_s.render(foot, True, (120, 128, 144))
        screen.blit(f, f.get_rect(center=(SCREEN_W / 2, SCREEN_H - 26)))

    def button(self, screen, r, label, desc="", enabled=True):
        hov = enabled and r.collidepoint(pygame.mouse.get_pos())
        screen.blit(art.button_img(r.w, r.h, 2 if not enabled else (1 if hov else 0)),
                    r.topleft)
        lab = self.font_b.render(label, True,
                                 (236, 240, 248) if enabled else (140, 146, 158))
        if desc:
            screen.blit(lab, lab.get_rect(center=(r.centerx, r.y + 20)))
            d = self.font_s.render(desc, True, (150, 158, 174))
            screen.blit(d, d.get_rect(center=(r.centerx, r.y + 44)))
        else:
            screen.blit(lab, lab.get_rect(center=r.center))
        return hov

    def line(self, screen, txt, y, color=(200, 208, 222), big=False, center=True, x=None):
        f = self.font_b if big else self.font
        s = f.render(txt, True, color)
        if x is None:
            x = SCREEN_W / 2 - (s.get_width() / 2 if center else 0)
        screen.blit(s, (x, y))


def menu(screen, clock, ui):
    """Écran principal : renvoie "solo" / "host" / "join" / None (quitter)."""
    if SMOKE:
        return "solo"
    items = [("solo", "Solo", "Affrontez l'intelligence artificielle"),
             ("host", "Héberger (LAN)", "Créez une partie sur le réseau local"),
             ("join", "Rejoindre (LAN)", "Rejoignez la partie d'un ami")]
    btns = [(pygame.Rect(SCREEN_W / 2 - 160, 348 + i * 82, 320, 64), key, lab, desc)
            for i, (key, lab, desc) in enumerate(items)]
    while True:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if global_key(e):
                continue
            if e.type == pygame.QUIT:
                return None
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return None
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for r, key, _lab, _desc in btns:
                    if r.collidepoint(e.pos):
                        return key
        ui.frame(screen, dt, "La Guerre des Cristaux — détruisez la base ennemie",
                 "Échap : quitter    F11 : plein écran")
        for r, _key, lab, desc in btns:
            ui.button(screen, r, lab, desc)
        pygame.display.flip()


def pick_difficulty(screen, clock, ui):
    """Sous-menu solo : renvoie une clé de difficulté ou None (retour)."""
    if SMOKE:
        return "normal"
    btns = [(pygame.Rect(SCREEN_W / 2 - 160, 348 + i * 82, 320, 64), key)
            for i, key in enumerate(["facile", "normal", "difficile"])]
    while True:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if global_key(e):
                continue
            if e.type == pygame.QUIT:
                return None
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return None
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for r, key in btns:
                    if r.collidepoint(e.pos):
                        return key
        ui.frame(screen, dt, "Choisissez la difficulté de l'IA")
        for r, key in btns:
            d = DIFFICULTES[key]
            ui.button(screen, r, d["nom"], d["desc"])
        pygame.display.flip()


def map_for_players(cfg):
    """La plus petite carte qui accepte le nombre de joueurs de la config."""
    n = len(cfg["players"])
    if n <= MAP_SIZES[cfg["map"]][3]:
        return cfg["map"]
    for key in ("petite", "moyenne", "grande"):
        if n <= MAP_SIZES[key][3]:
            return key
    return "grande"


def game_options(screen, clock, ui, subtitle="Options de la partie", lan=False):
    """Écran d'options à la création de partie : renvoie un dict config
    (voir data.DEFAULT_CONFIG) ou None (retour).
    En LAN les deux premiers slots sont les joueurs humains."""
    if SMOKE:
        return dict(DEFAULT_CONFIG)
    cfg = dict(DEFAULT_CONFIG)
    cfg["players"] = [dict(ai=False, team=1), dict(ai=not lan, team=2)]
    cx = SCREEN_W / 2
    lx, rx = cx - 344, cx + 24        # colonnes gauche (joueurs) et droite
    bar = pygame.Rect(rx, 384, 320, 12)
    zrow = pygame.Rect(rx, 428, 320, 26)
    map_btns = [(pygame.Rect(rx + i * 110, 496, 100, 42), key)
                for i, key in enumerate(("petite", "moyenne", "grande"))]
    play = pygame.Rect(rx, 570, 320, 56)
    dragging = False

    def set_speed(mx):
        cfg["speed"] = int(round(1 + clamp((mx - bar.x) / bar.w, 0, 1) * 299))

    def slot_rects():
        """(rangée, bouton équipe, bouton retirer) pour chaque slot."""
        out = []
        for i in range(len(cfg["players"])):
            y = 366 + i * 33
            out.append((pygame.Rect(lx, y, 320, 28),
                        pygame.Rect(lx + 176, y, 96, 28),
                        pygame.Rect(lx + 284, y, 36, 28)))
        return out

    def add_rect():
        return pygame.Rect(lx, 366 + len(cfg["players"]) * 33 + 6, 220, 34)

    while True:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if global_key(e):
                continue
            if e.type == pygame.QUIT:
                return None
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return None
            if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                return cfg
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if bar.inflate(12, 18).collidepoint(e.pos):
                    dragging = True
                    set_speed(e.pos[0])
                elif zrow.collidepoint(e.pos):
                    cfg["zombies"] = not cfg["zombies"]
                elif play.collidepoint(e.pos):
                    return cfg
                elif add_rect().collidepoint(e.pos) \
                        and len(cfg["players"]) < MAX_PLAYERS:
                    cfg["players"].append(dict(ai=True, team=len(cfg["players"]) + 1))
                    cfg["map"] = map_for_players(cfg)
                else:
                    for i, (_row, tr, xr) in enumerate(slot_rects()):
                        if tr.collidepoint(e.pos):
                            sl = cfg["players"][i]
                            sl["team"] = sl["team"] % MAX_PLAYERS + 1
                        elif xr.collidepoint(e.pos) and sl_removable(cfg, i, lan):
                            cfg["players"].pop(i)
                            break
                    for r, key in map_btns:
                        if r.collidepoint(e.pos) \
                                and len(cfg["players"]) <= MAP_SIZES[key][3]:
                            cfg["map"] = key
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                dragging = False
            if e.type == pygame.MOUSEMOTION and dragging:
                set_speed(e.pos[0])

        ui.frame(screen, dt, subtitle, "Échap : retour    Entrée : jouer")
        # --- colonne gauche : joueurs et équipes
        ui.line(screen, f"Joueurs ({len(cfg['players'])}/{MAX_PLAYERS}) — "
                "clic sur l'équipe pour la changer", 338, C_CRYSTAL, x=lx)
        for i, (row, tr, xr) in enumerate(slot_rects()):
            sl = cfg["players"][i]
            pygame.draw.rect(screen, (16, 18, 26), row)
            pygame.draw.rect(screen, (96, 108, 132), row, 1)
            col = art.PLAYER_COLORS[i]["main"]
            pygame.draw.rect(screen, col, (row.x + 6, row.y + 7, 14, 14))
            pygame.draw.rect(screen, (10, 12, 16), (row.x + 6, row.y + 7, 14, 14), 1)
            if i == 0:
                name = "Vous" + (" (hôte)" if lan else "")
            elif lan and i == 1:
                name = "Invité (LAN)"
            else:
                name = f"IA {i + 1}"
            ui.line(screen, name, row.y + 3, (216, 222, 232), x=row.x + 30)
            hov = tr.collidepoint(pygame.mouse.get_pos())
            screen.blit(art.button_img(tr.w, tr.h, 1 if hov else 0), tr.topleft)
            ui.line(screen, f"Équipe {sl['team']}", tr.y + 3, (226, 230, 238),
                    x=tr.x + 12)
            if sl_removable(cfg, i, lan):
                hov = xr.collidepoint(pygame.mouse.get_pos())
                screen.blit(art.button_img(xr.w, xr.h, 1 if hov else 0), xr.topleft)
                ui.line(screen, "✕", xr.y + 3, C_BAD, x=xr.x + 12)
        if len(cfg["players"]) < MAX_PLAYERS:
            r = add_rect()
            ui.button(screen, r, "+ Ajouter une IA")

        # --- colonne droite : vitesse, zombies, carte
        sp = cfg["speed"]
        label = "vitesse normale" if sp == 1 else f"ralenti ×{sp}"
        ui.line(screen, f"Vitesse de jeu : {label}", 352, (226, 230, 238), x=rx)
        pygame.draw.rect(screen, (16, 18, 26), bar)
        k = (sp - 1) / 299
        pygame.draw.rect(screen, (40, 120, 170), (bar.x, bar.y, int(bar.w * k), bar.h))
        pygame.draw.rect(screen, (96, 108, 132), bar, 1)
        hx = bar.x + int(bar.w * k)
        pygame.draw.circle(screen, (200, 236, 255), (hx, bar.centery), 9)
        pygame.draw.circle(screen, (30, 60, 80), (hx, bar.centery), 9, 2)
        box = pygame.Rect(zrow.x, zrow.y + 2, 22, 22)
        pygame.draw.rect(screen, (16, 18, 26), box)
        pygame.draw.rect(screen, (96, 108, 132), box, 1)
        if cfg["zombies"]:
            pygame.draw.lines(screen, (130, 230, 120), False,
                              [(box.x + 4, box.y + 11), (box.x + 9, box.y + 16),
                               (box.x + 18, box.y + 5)], 3)
        ui.line(screen, "Mode zombie : les unités mortes se relèvent",
                zrow.y + 3, (200, 208, 222), x=box.right + 12)
        ui.line(screen, "Taille de la carte :", 470, (200, 208, 222), x=rx)
        for r, key in map_btns:
            nom, mw, mh, cap = MAP_SIZES[key]
            ok = len(cfg["players"]) <= cap
            ui.button(screen, r, nom, enabled=ok)
            ui.line(screen, f"≤ {cap} joueurs", r.bottom + 4,
                    (150, 158, 174) if ok else C_BAD, x=r.x + 14)
            if key == cfg["map"]:
                pygame.draw.rect(screen, (110, 220, 255), r, 2, border_radius=5)
        ui.button(screen, play, "Jouer", "Entrée pour lancer la partie")
        pygame.display.flip()


def sl_removable(cfg, i, lan):
    """Un slot est supprimable s'il est une IA au-delà du minimum de 2 joueurs."""
    if i == 0 or (lan and i == 1):
        return False
    return len(cfg["players"]) > 2


def wait_handshake(peer, want, timeout=6.0):
    """Attend un message réseau de type `want` ; renvoie le message ou None."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout and peer.alive:
        for msg in peer.poll():
            if msg.get("t") == want:
                return msg
        time.sleep(0.02)
    return None


def lan_host(screen, clock, ui, cfg):
    """Héberge une partie : renvoie (peer, seed) ou None (retour).
    Les options `cfg` sont envoyées au client avec la seed (lockstep)."""
    try:
        listener = netcode.HostListener()
    except OSError:
        return show_net_error(screen, clock, ui,
                              "Impossible d'ouvrir le port " + str(netcode.TCP_PORT)
                              + " (déjà utilisé ?)")
    ip = netcode.local_ip()
    try:
        while True:
            dt = clock.tick(60) / 1000
            for e in pygame.event.get():
                if global_key(e):
                    continue
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN
                                             and e.key == pygame.K_ESCAPE):
                    return None
            peer = listener.poll()
            if peer is not None:
                listener.close()
                seed = random.randrange(1 << 30)
                peer.send(dict(t="hello", seed=seed, pid=1,
                               ver=list(sys.version_info[:2]), cfg=cfg))
                if wait_handshake(peer, "ready") is None:
                    peer.close()
                    return show_net_error(screen, clock, ui,
                                          "Le joueur ne répond pas.")
                return peer, seed
            ui.frame(screen, dt, "Partie en réseau local — vous serez l'Ordre d'Azur")
            dots = "." * (1 + int(ui.t * 2) % 3)
            ui.line(screen, "En attente d'un autre joueur" + dots, 380,
                    (226, 230, 238), big=True)
            ui.line(screen, f"Votre adresse : {ip}", 424, C_CRYSTAL, big=True)
            ui.line(screen, "Votre ami doit choisir « Rejoindre (LAN) » sur le même réseau.",
                    462, (150, 158, 174))
            pygame.display.flip()
    finally:
        listener.close()


def lan_join(screen, clock, ui):
    """Rejoint une partie : renvoie (peer, seed, cfg) ou None (retour)."""
    disco = netcode.Discovery()
    ip_text = ""
    error = ""

    def try_connect(ip):
        # affiche l'état pendant la connexion (bloquante, 3 s max)
        ui.frame(screen, 0, "Partie en réseau local")
        ui.line(screen, f"Connexion à {ip}…", 400, (226, 230, 238), big=True)
        pygame.display.flip()
        try:
            peer = netcode.connect(ip)
        except OSError:
            return None, "Connexion impossible à " + ip
        hello = wait_handshake(peer, "hello")
        if hello is None:
            peer.close()
            return None, "L'hôte ne répond pas."
        if hello.get("ver") != list(sys.version_info[:2]):
            print("Attention : versions de Python différentes entre les machines, "
                  "risque de désynchronisation.")
        peer.send(dict(t="ready"))
        return (peer, hello["seed"], hello.get("cfg", dict(DEFAULT_CONFIG))), ""

    try:
        while True:
            dt = clock.tick(60) / 1000
            hosts = disco.poll()
            host_btns = [(pygame.Rect(SCREEN_W / 2 - 160, 470 + i * 54, 320, 44), ip)
                         for i, ip in enumerate(hosts[:3])]
            for e in pygame.event.get():
                if global_key(e):
                    continue
                if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN
                                             and e.key == pygame.K_ESCAPE):
                    return None
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_RETURN and ip_text:
                        res, error = try_connect(ip_text)
                        if res is not None:
                            return res
                    elif e.key == pygame.K_BACKSPACE:
                        ip_text = ip_text[:-1]
                    elif e.unicode in "0123456789." and len(ip_text) < 15:
                        ip_text += e.unicode
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    for r, ip in host_btns:
                        if r.collidepoint(e.pos):
                            res, error = try_connect(ip)
                            if res is not None:
                                return res
            ui.frame(screen, dt, "Partie en réseau local — vous serez la Légion Karmin")
            ui.line(screen, "Adresse IP de l'hôte (Entrée pour rejoindre) :", 352,
                    (200, 208, 222))
            box = pygame.Rect(SCREEN_W / 2 - 160, 380, 320, 40)
            pygame.draw.rect(screen, (16, 18, 26), box)
            pygame.draw.rect(screen, (96, 108, 132), box, 1)
            cursor = "|" if int(ui.t * 2) % 2 == 0 else " "
            txt = ui.font_b.render(ip_text + cursor, True, (236, 240, 248))
            screen.blit(txt, (box.x + 12, box.y + 8))
            if hosts:
                ui.line(screen, "Parties détectées sur le réseau :", 444, C_CRYSTAL)
                for r, ip in host_btns:
                    ui.button(screen, r, ip)
            else:
                dots = "." * (1 + int(ui.t * 2) % 3)
                ui.line(screen, "Recherche de parties sur le réseau" + dots, 444,
                        (150, 158, 174))
            if error:
                ui.line(screen, error, SCREEN_H - 64, C_BAD)
            pygame.display.flip()
    finally:
        disco.close()


def show_net_error(screen, clock, ui, msg):
    t0 = time.monotonic()
    while time.monotonic() - t0 < 2.5:
        dt = clock.tick(60) / 1000
        for e in pygame.event.get():
            if e.type in (pygame.QUIT, pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return None
        ui.frame(screen, dt, "Partie en réseau local")
        ui.line(screen, msg, 400, C_BAD, big=True)
        pygame.display.flip()
    return None
