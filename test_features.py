# -*- coding: utf-8 -*-
"""
Suite de tests headless de CRISTALIS.

Lancer :  python test_features.py
Aucune fenêtre n'est ouverte (le flag --autotest force SDL_VIDEODRIVER=dummy).
Couvre : sanitize_config, mode Survie zombie (préparation, invasion,
remplacement, défaite, scores), menu pause / Échap, déterminisme de la sim.
"""

import os
import random
import sys
import tempfile
from types import SimpleNamespace

sys.argv.append("--autotest")  # data.py pose le driver vidéo dummy

import data  # noqa: E402  (premier import : mode headless)
import pygame  # noqa: E402

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
        px = w * data.TILE * h * data.TILE * 4
        assert px < 100e6, f"carte {key} trop grosse ({px/1e6:.0f} Mo de fond)"
        assert 2 <= cap <= data.MAX_PLAYERS
    print("OK tailles de cartes (mémoire bornée)")


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
    test_survie_preparation()
    test_survie_invasion_et_remplacement()
    test_survie_defaite_et_score()
    test_echap_et_menu_pause()
    test_determinisme()
    print("\nTous les tests sont passés.")
