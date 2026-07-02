# -*- coding: utf-8 -*-
"""
CRISTALIS — La Guerre des Cristaux
Un RTS en pygame : récoltez des cristaux, bâtissez votre base,
levez une armée et rasez les bases ennemies.

Lancer :  python cristalis.py
Test auto (IA vs IA, sans fenêtre) :  python cristalis.py --autotest

Point d'entrée et boucles de jeu uniquement — le reste est découpé en
modules : data (constantes), art (sprites), entities, ia, game (+ render),
menus, netcode.
"""

import random

import data  # premier import : pose SDL_VIDEODRIVER pour les modes headless

import pygame

# DEFAULT_CONFIG, MAP_SIZES et wait_handshake sont réexportés pour les
# scripts de test (mp_sim.py, test_features.py).
from data import (AUTOTEST, C_BAD, C_TEXT, DEFAULT_CONFIG, FACTION_NAMES,
                  MAP_SIZES, NET_DELAY, SCREEN_H, SCREEN_W, SMOKE, TICK_DT,
                  VERSION, VIEW_H)
from game import Game
from menus import (MenuUI, game_options, global_key, lan_host, lan_join, menu,
                   pick_difficulty, wait_handshake)


def run_autotest():
    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H))
    random.seed(42)
    game = Game("normal", p0_ai=True)
    steps = 0
    dt = 1 / 20
    while game.winner is None and steps < 20 * 60 * 45:
        game.update(dt)
        steps += 1
        if steps % (20 * 60) == 0:
            p0, p1 = game.players[0], game.players[1]
            print(f"t={steps // 20}s  crist={p0.crystals}/{p1.crystals}  "
                  f"unités={sum(u.owner is p0 for u in game.units)}/"
                  f"{sum(u.owner is p1 for u in game.units)}  "
                  f"bât={sum(b.owner is p0 for b in game.buildings)}/"
                  f"{sum(b.owner is p1 for b in game.buildings)}")
    if game.winner is None:
        print("AUTOTEST: pas de vainqueur en 45 min simulées")
    else:
        names = [FACTION_NAMES[p.pid] for p in game.combatants
                 if p.team == game.winner]
        print(f"AUTOTEST OK — équipe gagnante : {game.winner} "
              f"({', '.join(names)}) à t={int(game.time)}s")
    pygame.quit()


def run_solo(screen, clock, diff, config=None):
    """Boucle solo classique : renvoie "menu" ou "quit"."""
    game = Game(diff, config=config)
    smoke_frames = 0
    while True:
        dt = min(clock.tick(60) / 1000, 0.05)
        for e in pygame.event.get():
            if global_key(e):
                continue
            if e.type == pygame.QUIT:
                return "quit"
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE \
                    and game.winner is not None:
                return "quit"
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r \
                    and game.winner is not None:
                return "menu"
            game.handle_event(e)
        game.scroll(dt, pygame.key.get_pressed())
        game.update(dt / game.speed)
        game.draw(screen)
        pygame.display.flip()
        if SMOKE:
            smoke_frames += 1
            if smoke_frames > 240:
                return "quit"


def run_multiplayer(screen, clock, peer, local_pid, seed, config=None):
    """Boucle LAN en lockstep : les deux machines simulent la même partie
    et n'échangent que les commandes des joueurs. Renvoie "menu" ou "quit"."""
    random.seed(seed)
    game = Game(multiplayer=True, local_pid=local_pid, config=config)
    game.net = peer
    remote_pid = 1 - local_pid
    # le ralenti étire la durée réelle d'un tick (la sim reste à TICK_DT)
    period = TICK_DT * game.speed
    # bundles[tick][pid] = liste de commandes ; les premiers ticks sont vides
    bundles = {t: {0: [], 1: []} for t in range(NET_DELAY)}
    my_hashes = {}
    acc = 0.0
    sent_until = 0
    stall = 0.0
    desync = False
    while True:
        dt = min(clock.tick(60) / 1000, 0.1)
        for e in pygame.event.get():
            if global_key(e):
                continue
            if e.type == pygame.QUIT:
                peer.send(dict(t="bye"))
                return "quit"
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE \
                    and (game.winner is not None or not peer.alive):
                peer.send(dict(t="bye"))
                return "menu"
            game.handle_event(e)

        for msg in peer.poll():
            mt = msg.get("t")
            if mt == "tick":
                bundles.setdefault(msg["n"], {})[remote_pid] = msg["cmds"]
                if "h" in msg:
                    ht = msg["ht"]
                    if ht in my_hashes and my_hashes[ht] != msg["h"] and not desync:
                        desync = True
                        game.message("⚠ Désynchronisation détectée !", C_BAD, 10)
            elif mt == "bye":
                peer.alive = False

        game.scroll(dt, pygame.key.get_pressed())
        acc = min(acc + dt, 4 * period)
        waiting = False
        while acc >= period:
            t = game.tick
            if sent_until <= t:
                out = dict(t="tick", n=t + NET_DELAY, cmds=game.outbox)
                if t % 100 == 0:
                    h = game.state_hash()
                    my_hashes[t] = h
                    out["ht"], out["h"] = t, h
                    for old in [k for k in my_hashes if k < t - 1000]:
                        del my_hashes[old]
                peer.send(out)
                bundles.setdefault(t + NET_DELAY, {})[local_pid] = game.outbox
                game.outbox = []
                sent_until = t + 1
            b = bundles.get(t, {})
            if remote_pid not in b:
                if not peer.alive:
                    acc = 0.0
                waiting = True
                break  # on attend le paquet de l'adversaire
            for pid in (0, 1):
                for cmd in b.get(pid, []):
                    game.apply_command(cmd)
            bundles.pop(t, None)
            game.update(TICK_DT)
            game.tick = t + 1
            acc -= period
        stall = stall + dt if waiting else 0.0

        game.draw(screen)
        if game.winner is None:
            if not peer.alive:
                s = pygame.Surface((SCREEN_W, VIEW_H), pygame.SRCALPHA)
                s.fill((8, 10, 16, 170))
                screen.blit(s, (0, 0))
                game.text(screen, game.font_h, "Connexion perdue", C_BAD,
                          SCREEN_W // 2, VIEW_H // 2 - 60, center=True)
                game.text(screen, game.font_b, "Échap : retour au menu", C_TEXT,
                          SCREEN_W // 2, VIEW_H // 2 + 10, center=True)
            elif stall > 0.5:
                game.text(screen, game.font_b, "En attente de l'adversaire…", C_TEXT,
                          SCREEN_W // 2, VIEW_H // 2 - 20, center=True)
        pygame.display.flip()


def main():
    if AUTOTEST:
        run_autotest()
        return
    pygame.mixer.pre_init(22050, -16, 2, 256)
    pygame.init()
    # SCALED : résolution logique fixe 1280×720, le plein écran (F11) ne fait
    # qu'étirer l'image — coordonnées souris et rendu inchangés.
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H),
                                     0 if SMOKE else pygame.SCALED)
    pygame.display.set_caption(f"CRISTALIS — La Guerre des Cristaux (v{VERSION})")
    clock = pygame.time.Clock()
    ui = MenuUI()
    while True:
        choice = menu(screen, clock, ui)
        if choice is None:
            break
        if choice == "solo":
            diff = pick_difficulty(screen, clock, ui)
            if diff is None:
                continue
            cfg = game_options(screen, clock, ui)
            if cfg is None:
                continue
            if run_solo(screen, clock, diff, cfg) == "quit":
                break
        elif choice == "host":
            cfg = game_options(screen, clock, ui, "Options de la partie (hôte)",
                               lan=True)
            if cfg is None:
                continue
            res = lan_host(screen, clock, ui, cfg)
            if res is None:
                continue
            peer, seed = res
            outcome = run_multiplayer(screen, clock, peer, 0, seed, cfg)
            peer.close()
            if outcome == "quit":
                break
        elif choice == "join":
            res = lan_join(screen, clock, ui)
            if res is None:
                continue
            peer, seed, cfg = res
            outcome = run_multiplayer(screen, clock, peer, 1, seed, cfg)
            peer.close()
            if outcome == "quit":
                break
    pygame.quit()


if __name__ == "__main__":
    main()
