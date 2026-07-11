# -*- coding: utf-8 -*-
"""
Suite de tests headless de CRISTALIS.

Lancer :  python test_features.py
Aucune fenêtre n'est ouverte (le flag --autotest force SDL_VIDEODRIVER=dummy).
Couvre : sanitize_config, terrain chunké, opérations de brouillard, mode
Survie zombie (préparation, invasion, remplacement, défaite, scores), menu
pause / Échap, déterminisme de la sim, relais Internet (codes de partie,
appariement, handshake hello/ready/go, NET_DELAY adaptatif).
"""

import asyncio
import os
import random
import sys
import tempfile
import threading
from types import SimpleNamespace

sys.argv.append("--autotest")  # data.py pose le driver vidéo dummy

import data  # noqa: E402  (premier import : mode headless)
import pygame  # noqa: E402
import art  # noqa: E402

pygame.init()
pygame.display.set_mode((data.SCREEN_W, data.SCREEN_H))

import game as game_mod  # noqa: E402
from game import Game, sanitize_config  # noqa: E402

DT = 1 / 20


def new_survie(map_key="petite", spawn=5, prep=0, score_path=None):
    cfg = dict(data.DEFAULT_CONFIG, map=map_key, zombie_spawn_interval=spawn,
               zombie_invasion_delay=prep, players=[dict(ai=False, team=1)])
    if score_path is not None:
        game_mod.Game.survival_score_path = property(lambda self: score_path)
    return Game("survie", config=cfg)


def run(g, seconds):
    for _ in range(int(seconds / DT)):
        g.update(DT)


def zombie_count(g):
    return sum(1 for u in g.units if u.owner is g.zombie_p and u.kind == "zombie")


def test_sanitize_config():
    cfg = sanitize_config(dict(zombie_spawn_interval=1, zombie_invasion_delay=9999,
                               map="inexistante", speed=0))
    assert cfg["zombie_spawn_interval"] == 5, cfg
    assert cfg["zombie_invasion_delay"] == 600, cfg
    assert cfg["map"] == "moyenne", cfg
    assert cfg["speed"] == 1, cfg
    assert len(cfg["players"]) >= 2, cfg
    print("OK sanitize_config")


def test_map_sizes():
    for key, (_nom, w, h, cap) in data.MAP_SIZES.items():
        assert 2 <= cap <= data.MAX_PLAYERS
    # le fond est chunké (art.Terrain) : la mémoire est bornée par le cache
    # LRU quelle que soit la taille de la carte
    cache = art.TERRAIN_MAX_CHUNKS * art.TERRAIN_CHUNK ** 2 * 4
    assert cache < 100e6, f"cache de chunks trop gros ({cache/1e6:.0f} Mo)"
    print("OK tailles de cartes (fond chunké, mémoire bornée)")


def test_terrain_chunks():
    tile = data.TILE
    t1 = art.Terrain(4096, 2048, tile, seed=7)
    t2 = art.Terrain(4096, 2048, tile, seed=7)
    ref = pygame.image.tobytes(t1.chunk(3, 2), "RGB")
    assert ref == pygame.image.tobytes(t2.chunk(3, 2), "RGB"), \
        "deux terrains de même graine diffèrent"
    # après éviction LRU, un chunk régénéré doit être identique
    for i in range(art.TERRAIN_MAX_CHUNKS + 5):
        t1.chunk(i % 16, 4 + i // 16)
    assert (3, 2) not in t1.chunks, "chunk non évincé du cache LRU"
    assert len(t1.chunks) <= art.TERRAIN_MAX_CHUNKS
    assert pygame.image.tobytes(t1.chunk(3, 2), "RGB") == ref, \
        "chunk régénéré différent de l'original"
    # une place cuite (bake) doit apparaître même après régénération
    before = pygame.image.tobytes(t1.chunk(0, 0), "RGB")
    art.bake_plaza(t1, 128, 128, 60)
    assert pygame.image.tobytes(t1.chunk(0, 0), "RGB") != before, \
        "l'overlay cuit n'apparaît pas dans le chunk"
    # draw couvre toute la vue, y compris contre les bords de carte
    view = pygame.Surface((data.VIEW_W, data.VIEW_H))
    view.fill((255, 0, 255))
    t1.draw(view, pygame.math.Vector2(4096 - data.VIEW_W, 2048 - data.VIEW_H))
    for p in ((0, 0), (data.VIEW_W - 1, data.VIEW_H - 1),
              (data.VIEW_W // 2, data.VIEW_H // 2)):
        assert view.get_at(p)[:3] != (255, 0, 255), f"trou dans le fond en {p}"
    assert t1.minimap(210, 130).get_size() == (210, 130)
    print("OK terrain chunké : déterminisme, LRU, overlays, bords de carte")


def test_fog_ops():
    """Les fusions d'octets du brouillard (exploré |= visible, voile minimap)
    doivent équivaloir aux anciennes boucles case par case."""
    random.seed(9)
    g = Game("normal")
    old = game_mod.AUTOTEST
    game_mod.AUTOTEST = False  # update_fog est court-circuité en autotest
    try:
        g.fog_explored = bytearray(len(g.fog_explored))
        g.update_fog()
        vis, exp = g.fog_visible, g.fog_explored
        assert any(vis), "aucune case visible autour de la base"
        assert set(exp) <= {0, 1} and set(vis) <= {0, 1}
        assert all(e >= v for e, v in zip(exp, vis)), \
            "case visible non marquée explorée"
        g._fog_mini = None
        g.draw_minimap(pygame.display.get_surface())
        assert g._fog_mini[0] == g.fog_version
    finally:
        game_mod.AUTOTEST = old
    print("OK brouillard : fusion exploré/visible et voile minimap")


def test_survie_preparation():
    random.seed(3)
    g = new_survie(prep=30)
    assert not g.survival_started
    run(g, 10)
    assert zombie_count(g) == 0, "zombie apparu pendant la préparation"
    assert g.survival_time == 0.0
    run(g, 25)
    assert g.survival_started, "l'invasion n'a pas démarré après le délai"
    assert g.survival_time > 0
    print("OK survie : phase de préparation")


def test_survie_invasion_et_remplacement():
    random.seed(4)
    g = new_survie(spawn=5, prep=0)
    assert g.survival_started
    run(g, 21)
    assert g.survival_target == 4, g.survival_target
    assert zombie_count(g) == 4, zombie_count(g)
    # un zombie meurt : il doit être remplacé immédiatement (cible maintenue)
    z = next(u for u in g.units if u.owner is g.zombie_p)
    g.kill_unit(z)
    run(g, 1)
    assert zombie_count(g) >= 4, "zombie mort non remplacé"
    print("OK survie : invasion et remplacement des morts")


def test_survie_defaite_et_score():
    tmp = os.path.join(tempfile.gettempdir(), "cristalis_test_scores.json")
    if os.path.exists(tmp):
        os.remove(tmp)
    random.seed(5)
    g = new_survie(spawn=5, prep=0, score_path=tmp)
    run(g, 5)
    for b in list(g.buildings):  # la horde "rase" la base
        if b.owner is g.me:
            g.destroy_building(b)
    run(g, 1)
    assert g.winner == data.ZOMBIE_TEAM, g.winner
    assert os.path.exists(tmp), "score non sauvegardé"
    assert g.survival_new_record, "première partie = record attendu"
    best = g.survival_best
    # deuxième partie plus courte : pas de record, best inchangé
    random.seed(5)
    g2 = new_survie(spawn=5, prep=0, score_path=tmp)
    run(g2, 2)
    for b in list(g2.buildings):
        if b.owner is g2.me:
            g2.destroy_building(b)
    run(g2, 1)
    assert not g2.survival_new_record
    assert g2.survival_best == best
    os.remove(tmp)
    print("OK survie : défaite, sauvegarde et record")


def key_event(key):
    return SimpleNamespace(type=pygame.KEYDOWN, key=key)


def click_event(pos):
    return SimpleNamespace(type=pygame.MOUSEBUTTONDOWN, button=1, pos=pos)


def test_echap_et_menu_pause():
    random.seed(6)
    g = Game("normal")
    # Échap sans sélection ni placement : ouvre le menu pause
    g.handle_event(key_event(pygame.K_ESCAPE))
    assert g.paused, "Échap n'a pas ouvert le menu pause"
    # Échap dans le menu pause : reprise
    g.handle_event(key_event(pygame.K_ESCAPE))
    assert not g.paused, "Échap n'a pas fermé le menu pause"
    # Échap avec une sélection : désélectionne sans mettre en pause
    g.selection = list(g.units[:1])
    g.handle_event(key_event(pygame.K_ESCAPE))
    assert not g.selection and not g.paused
    # clic sur QUITTER dans le menu pause : demande de retour menu
    g.handle_event(key_event(pygame.K_p))
    assert g.paused
    _panel, _resume, quit_r = g.pause_menu_rects()
    g.handle_event(click_event(quit_r.center))
    assert g.request_return_menu, "QUITTER n'a pas demandé le retour menu"
    # écran de fin : Échap = retour menu
    random.seed(6)
    g = Game("normal")
    g.winner = 1
    g.handle_event(key_event(pygame.K_ESCAPE))
    assert g.request_return_menu
    print("OK Échap / menu pause / QUITTER / écran de fin")


def test_net_delay_et_parse_addr():
    import netcode
    assert netcode.pick_net_delay(0.0) == netcode.NET_DELAY_MIN
    assert netcode.pick_net_delay(0.3) == 7      # 300 ms → 6 ticks + 1
    assert netcode.pick_net_delay(60.0) == netcode.NET_DELAY_MAX
    assert netcode.parse_addr("10.0.0.2") == ("10.0.0.2", netcode.TCP_PORT)
    assert netcode.parse_addr("10.0.0.2:8123") == ("10.0.0.2", 8123)
    assert netcode.parse_addr("hote.fr:x") == ("hote.fr", netcode.TCP_PORT)
    print("OK net_delay adaptatif et parse_addr")


def test_relais_internet():
    """Serveur relais local + vrai handshake réseau : code de partie,
    appariement, hello/ready/go, tuyau transparent, code inconnu."""
    import netcode
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    import relay

    loop = asyncio.new_event_loop()
    started = threading.Event()
    info = {}

    def run_loop():
        asyncio.set_event_loop(loop)
        srv = loop.run_until_complete(relay.serve(port=0, host="127.0.0.1"))
        info["port"] = srv.sockets[0].getsockname()[1]
        started.set()
        loop.run_forever()

    threading.Thread(target=run_loop, daemon=True).start()
    assert started.wait(5), "le relais ne démarre pas"
    addr = f"127.0.0.1:{info['port']}"

    # code inconnu → refus propre
    p, err = netcode.relay_join("ZZZZ-9", addr)
    assert p is None and err, (p, err)

    # hébergement : le relais fournit un code de partie
    host_peer, code = netcode.relay_host(addr)
    assert host_peer is not None and "-" in code, code

    cfg = dict(data.DEFAULT_CONFIG)
    result = {}

    def host_side():
        if netcode.wait_msg(host_peer, "paired", 8) is not None:
            result["nd"] = netcode.host_handshake(host_peer, 1234, cfg,
                                                  sys.version_info[:2])

    ht = threading.Thread(target=host_side, daemon=True)
    ht.start()
    join_peer, err = netcode.relay_join(code, addr)
    assert join_peer is not None, err
    res = netcode.join_handshake(join_peer)
    assert res is not None, "handshake invité échoué"
    hello, nd = res
    ht.join(10)
    assert result.get("nd") == nd and nd >= netcode.NET_DELAY_MIN, (result, nd)
    assert hello["seed"] == 1234 and hello["cfg"]["map"] == cfg["map"]

    # après appariement le relais est un tuyau transparent, dans les 2 sens
    host_peer.send(dict(t="tick", n=3, cmds=[]))
    msg = netcode.wait_msg(join_peer, "tick", 5)
    assert msg is not None and msg["n"] == 3, msg
    join_peer.send(dict(t="ka"))
    assert netcode.wait_msg(host_peer, "ka", 5) is not None
    assert join_peer.last_recv > 0  # keepalive : horodatage de réception tenu

    host_peer.close()
    join_peer.close()
    loop.call_soon_threadsafe(loop.stop)
    print("OK relais Internet : code, appariement, handshake, tuyau transparent")


def test_determinisme():
    """Deux sims identiques (même seed) doivent rester synchrones : garde-fou
    lockstep, vérifie que les nouveautés ne consomment pas le RNG en partie
    normale de façon divergente."""
    hashes = []
    for _ in range(2):
        random.seed(7)
        Gm = Game("normal", p0_ai=True)
        run(Gm, 30)
        hashes.append(Gm.state_hash())
    assert hashes[0] == hashes[1], "désynchronisation : sim non déterministe"
    print("OK déterminisme (state_hash identiques)")


if __name__ == "__main__":
    test_sanitize_config()
    test_map_sizes()
    test_terrain_chunks()
    test_fog_ops()
    test_survie_preparation()
    test_survie_invasion_et_remplacement()
    test_survie_defaite_et_score()
    test_echap_et_menu_pause()
    test_net_delay_et_parse_addr()
    test_relais_internet()
    test_determinisme()
    print("\nTous les tests sont passés.")
