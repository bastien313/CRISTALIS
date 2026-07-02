# -*- coding: utf-8 -*-
"""
CRISTALIS — La Guerre des Cristaux
Un RTS en pygame : récoltez des cristaux, bâtissez votre base,
levez une armée et rasez la base ennemie.

Lancer :  python cristalis.py
Test auto (IA vs IA, sans fenêtre) :  python cristalis.py --autotest
"""

import heapq
import math
import os
import random
import sys
import time
import zlib

AUTOTEST = "--autotest" in sys.argv
SMOKE = os.environ.get("CRISTALIS_SMOKE") == "1"
if AUTOTEST or SMOKE:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame
from pygame.math import Vector2

import art
import netcode
from art import PLAYER_COLORS, clamp, mix, shade, lightc

TILE = 32
# Taille de carte par défaut ; modifiée par set_map_size() AVANT de créer Game.
MAP_W, MAP_H = 64, 44
WORLD_W, WORLD_H = MAP_W * TILE, MAP_H * TILE
MAP_SIZES = {"petite": ("Petite", 48, 34), "moyenne": ("Moyenne", 64, 44),
             "grande": ("Grande", 96, 64)}
SCREEN_W, SCREEN_H = 1280, 720
HUD_H = 170
VIEW_W, VIEW_H = SCREEN_W, SCREEN_H - HUD_H
TOPBAR_H = 30
EDGE_SCROLL = 18
CAM_SPEED = 520

# Multijoueur : simulation à pas fixe, les commandes émises au tick T
# sont exécutées au tick T + NET_DELAY sur les deux machines.
TICK_DT = 1 / 20
NET_DELAY = 3

# Options de partie : identiques des deux côtés en LAN (l'hôte les envoie
# au client avec la seed dans le message "hello").
DEFAULT_CONFIG = dict(speed=1, zombies=False, map="moyenne")
TOMB_DELAY = 20.0  # secondes entre la mort d'une unité et le zombie
ZOMBIE_PID = 2     # joueur neutre hostile, jamais dans la condition de victoire


def set_map_size(key):
    global MAP_W, MAP_H, WORLD_W, WORLD_H
    _nom, MAP_W, MAP_H = MAP_SIZES.get(key, MAP_SIZES["moyenne"])
    WORLD_W, WORLD_H = MAP_W * TILE, MAP_H * TILE

C_TEXT = (226, 230, 238)
C_DIM = (148, 156, 172)
C_CRYSTAL = (96, 220, 255)
C_GOOD = (118, 224, 128)
C_BAD = (238, 96, 84)
C_GOLD = (238, 210, 120)

FACTION_NAMES = ["Ordre d'Azur", "Légion Karmin"]
AI_NAMES = ["Seigneur Vhrax", "Générale Onyx", "Archonte Malgrim"]

# ------------------------------------------------------------------- données
UNIT_TYPES = {
    "ouvrier": dict(nom="Ouvrier", cout=50, hp=45, degats=4, portee=16, vitesse=82,
                    cooldown=1.0, supply=1, rayon=8, tps=6.0, aggro=0, splash=0,
                    desc="Récolte les cristaux et construit les bâtiments."),
    "soldat": dict(nom="Soldat", cout=75, hp=105, degats=10, portee=20, vitesse=74,
                   cooldown=0.85, supply=1, rayon=10, tps=8.0, aggro=150, splash=0,
                   desc="Combattant de mêlée robuste et bon marché."),
    "archer": dict(nom="Archer", cout=110, hp=55, degats=9, portee=150, vitesse=68,
                   cooldown=1.05, supply=1, rayon=9, tps=10.0, aggro=175, splash=0,
                   desc="Tireur à distance, fragile mais mortel en groupe."),
    "mage": dict(nom="Mage cristallin", cout=165, hp=50, degats=20, portee=165, vitesse=58,
                 cooldown=2.3, supply=2, rayon=9, tps=14.0, aggro=180, splash=44,
                 desc="Projette des éclats de cristal : dégâts de zone."),
    "golem": dict(nom="Golem de quartz", cout=240, hp=350, degats=25, portee=24, vitesse=45,
                  cooldown=1.35, supply=3, rayon=15, tps=18.0, aggro=140, splash=0,
                  desc="Colosse de pierre, absorbe les coups en première ligne."),
    "baliste": dict(nom="Baliste", cout=230, hp=95, degats=28, portee=235, vitesse=44,
                    cooldown=3.2, supply=3, rayon=12, tps=18.0, aggro=190, splash=0,
                    desc="Engin de siège : dégâts triplés contre les bâtiments."),
    "zombie": dict(nom="Zombie", cout=0, hp=90, degats=9, portee=16, vitesse=40,
                   cooldown=1.1, supply=0, rayon=9, tps=8.0, aggro=260, splash=0,
                   desc="Mort-vivant : attaque tout ce qui vit à proximité."),
}

BUILDING_TYPES = {
    "qg": dict(nom="Quartier Général", cout=400, hp=950, taille=(4, 3), supply=10,
               prod=["ouvrier"], build_time=45, depot=True, degats=0, portee=0, cooldown=0,
               desc="Cœur de la base : produit les ouvriers, reçoit les cristaux."),
    "obelisque": dict(nom="Obélisque", cout=100, hp=260, taille=(1, 2), supply=8,
                      prod=[], build_time=13, depot=False, degats=0, portee=0, cooldown=0,
                      desc="Canalise l'énergie : +8 de ravitaillement."),
    "caserne": dict(nom="Caserne", cout=150, hp=550, taille=(3, 2), supply=0,
                    prod=["soldat"], build_time=20, depot=False, degats=0, portee=0, cooldown=0,
                    desc="Forme les soldats de mêlée."),
    "archerie": dict(nom="Archerie", cout=180, hp=480, taille=(3, 2), supply=0,
                     prod=["archer", "mage"], build_time=24, depot=False, degats=0, portee=0,
                     cooldown=0, desc="Forme archers et mages cristallins."),
    "forge": dict(nom="Forge à golems", cout=260, hp=650, taille=(3, 3), supply=0,
                  prod=["golem", "baliste"], build_time=30, depot=False, degats=0, portee=0,
                  cooldown=0, desc="Assemble les golems de quartz et les balistes."),
    "tour": dict(nom="Tour de cristal", cout=130, hp=380, taille=(2, 2), supply=0,
                 prod=[], build_time=17, depot=False, degats=13, portee=190, cooldown=0.95,
                 desc="Défense automatique : foudroie les ennemis proches."),
    "sanctuaire": dict(nom="Sanctuaire", cout=200, hp=500, taille=(2, 2), supply=0,
                       prod=["up_atq", "up_def"], build_time=22, depot=False, degats=0,
                       portee=0, cooldown=0,
                       desc="Recherche les améliorations d'attaque et de défense."),
    "muraille": dict(nom="Muraille", cout=25, hp=260, taille=(1, 1), supply=0,
                     prod=[], build_time=6, depot=False, degats=0, portee=0, cooldown=0,
                     desc="Rempart de pierre qui bloque le passage."),
    "porte": dict(nom="Porte", cout=50, hp=240, taille=(1, 1), supply=0,
                  prod=[], build_time=8, depot=False, degats=0, portee=0, cooldown=0,
                  desc="Ne s'ouvre que pour laisser passer vos unités."),
}

# Améliorations recherchées au Sanctuaire (3 niveaux chacune).
UPGRADE_TYPES = {
    "up_atq": dict(nom="Attaque", cout=150, tps=25.0, max=3,
                   desc="Dégâts de vos unités +15% par niveau."),
    "up_def": dict(nom="Défense", cout=150, tps=25.0, max=3,
                   desc="Dégâts subis par vos unités -12% par niveau."),
}

WALL_KINDS = ("muraille", "porte")


def prod_stats(kind):
    return UPGRADE_TYPES[kind] if kind in UPGRADE_TYPES else UNIT_TYPES[kind]


BUILD_MENU = ["qg", "obelisque", "caserne", "archerie", "forge", "tour",
              "sanctuaire", "muraille", "porte"]
BUILD_HOTKEYS = {"qg": pygame.K_g, "obelisque": pygame.K_o, "caserne": pygame.K_c,
                 "archerie": pygame.K_r, "forge": pygame.K_f, "tour": pygame.K_t,
                 "sanctuaire": pygame.K_s, "muraille": pygame.K_m, "porte": pygame.K_e}
PROD_HOTKEYS = {"ouvrier": pygame.K_o, "soldat": pygame.K_s, "archer": pygame.K_a,
                "mage": pygame.K_m, "golem": pygame.K_g, "baliste": pygame.K_b,
                "up_atq": pygame.K_a, "up_def": pygame.K_d}

# tempo : divise l'horloge du plan de construction de l'IA (plus grand = plus lent)
# wave_max : taille maximale des vagues d'attaque de l'IA
DIFFICULTES = {
    "facile": dict(nom="Facile", income=0.55, workers=6, wave0=5, wave_step=1,
                   prod_pause=9.0, tempo=1.6, wave_max=12,
                   desc="L'IA prend vraiment son temps. Idéal pour apprendre."),
    "normal": dict(nom="Normal", income=1.0, workers=11, wave0=9, wave_step=3,
                   prod_pause=2.0, tempo=1.0, wave_max=24,
                   desc="Un adversaire équilibré."),
    "difficile": dict(nom="Difficile", income=1.25, workers=14, wave0=11, wave_step=4,
                      prod_pause=0.0, tempo=1.0, wave_max=26,
                      desc="L'IA est agressive et efficace. Bonne chance."),
}


def dist_point_rect(p, rect):
    cx = clamp(p.x, rect.left, rect.right)
    cy = clamp(p.y, rect.top, rect.bottom)
    return math.hypot(p.x - cx, p.y - cy)


# --------------------------------------------------------------------- sons
def build_sounds():
    sounds = {}
    try:
        import numpy as np
        rate = 22050

        def tone(freqs, dur, vol=0.22, decay=6.0, noise=0.0):
            n = int(rate * dur)
            t = np.linspace(0, dur, n, False)
            w = np.zeros(n)
            for f in freqs:
                w += np.sin(2 * math.pi * f * t)
            if noise:
                w += noise * np.random.uniform(-1, 1, n)
            w *= np.exp(-decay * t) * vol / max(1, len(freqs))
            arr = (w * 32767).astype(np.int16)
            return pygame.sndarray.make_sound(np.column_stack([arr, arr]).copy())

        sounds["click"] = tone([880], 0.06, 0.15, 22)
        sounds["place"] = tone([220, 330], 0.18, 0.2, 10)
        sounds["depot"] = tone([1040, 1560], 0.1, 0.14, 18)
        sounds["hit"] = tone([160], 0.08, 0.18, 18, noise=0.5)
        sounds["magic"] = tone([700, 1050], 0.22, 0.16, 9)
        sounds["die"] = tone([120, 90], 0.3, 0.2, 8, noise=0.4)
        sounds["done"] = tone([523, 659, 784], 0.3, 0.16, 6)
        sounds["alert"] = tone([440, 330, 440, 330], 0.5, 0.22, 3)
        sounds["win"] = tone([523, 659, 784, 1046], 0.8, 0.2, 2)
        sounds["lose"] = tone([330, 262, 196], 0.9, 0.2, 2)
    except Exception:
        pass
    return sounds


# ----------------------------------------------------------------- entités
class Player:
    def __init__(self, pid, is_ai, income_mult=1.0):
        self.pid = pid
        self.is_ai = is_ai
        self.crystals = 300
        self.income_mult = income_mult
        self.colors = PLAYER_COLORS[pid]
        self.total_gathered = 0
        self.units_lost = 0
        self.units_killed = 0
        self.atk_level = 0
        self.def_level = 0

    def upgrade_level(self, kind):
        return self.atk_level if kind == "up_atq" else self.def_level

    def supply_used(self, game):
        used = sum(UNIT_TYPES[u.kind]["supply"] for u in game.units if u.owner is self)
        for b in game.buildings:
            if b.owner is self:
                used += sum(UNIT_TYPES[k]["supply"] for k in b.queue if k in UNIT_TYPES)
        return used

    def supply_cap(self, game):
        cap = sum(BUILDING_TYPES[b.kind]["supply"] for b in game.buildings
                  if b.owner is self and b.done)
        return min(cap, 90)


class Doodad:
    """Arbre ou rocher : décor bloquant, trié en profondeur."""

    def __init__(self, kind, x, y, seed):
        self.kind = kind
        self.pos = Vector2(x, y)
        self.sprite = art.tree_sprite(seed) if kind == "tree" else art.rock_sprite(seed)
        self.r = 9 if kind == "tree" else 8
        self.sort_y = y

    def draw(self, view, cam, game):
        p = self.pos - cam
        if not (-60 < p.x < VIEW_W + 60 and -70 < p.y < VIEW_H + 40):
            return
        if self.kind == "tree":
            sh = art.shadow_tex(34, 13)
            view.blit(sh, sh.get_rect(center=(p.x + 3, p.y + 4)))
            view.blit(self.sprite, self.sprite.get_rect(midbottom=(p.x, p.y + 7)))
        else:
            sh = art.shadow_tex(28, 11)
            view.blit(sh, sh.get_rect(center=(p.x + 2, p.y + 4)))
            view.blit(self.sprite, self.sprite.get_rect(center=(p.x, p.y - 2)))


class Crystal:
    def __init__(self, x, y, amount):
        self.pos = Vector2(x, y)
        self.amount = amount
        self.max_amount = amount
        self.seed = random.random() * 10
        self.sort_y = y + 6

    @property
    def radius(self):
        return 9 + 8 * (self.amount / self.max_amount)

    def draw(self, view, cam, game):
        p = self.pos - cam
        if not (-50 < p.x < VIEW_W + 50 and -50 < p.y < VIEW_H + 50):
            return
        ratio = 0.45 + 0.55 * (self.amount / self.max_amount)
        pulse = 0.7 + 0.3 * math.sin(game.time * 2.2 + self.seed)
        g = art.glow((14, 52, 66), int(26 * ratio) + 6)
        view.blit(g, g.get_rect(center=(p.x, p.y)), special_flags=pygame.BLEND_ADD)
        sh = art.shadow_tex(int(34 * ratio) + 8, 12)
        view.blit(sh, sh.get_rect(center=(p.x, p.y + 8)))
        rng = random.Random(int(self.seed * 1000))
        cols = [(96, 216, 255), (140, 232, 255), (76, 190, 240)]
        for i in range(3):
            a = self.seed + i * 2.1
            ox = math.cos(a) * 8 * ratio
            oy = math.sin(a) * 5 * ratio
            w = (5 + rng.uniform(0, 2)) * ratio
            h = (13 + rng.uniform(0, 5)) * ratio * (1 + 0.04 * math.sin(game.time * 2 + i))
            art.draw_shard(view, p.x + ox, p.y + oy - h * 0.2, w, h, cols[i])
        for i in range(4):
            a = self.seed * 3 + i * 1.7
            view.set_at((int(p.x + math.cos(a) * 14 * ratio),
                         int(p.y + 8 + math.sin(a) * 3)), (150, 220, 240)) \
            if 0 <= p.x + math.cos(a) * 14 * ratio < VIEW_W - 1 and 0 <= p.y + 8 + math.sin(a) * 3 < VIEW_H - 1 else None
        # étincelle de lueur au sommet
        g2 = art.glow((30, 90, 110), int(8 + 3 * pulse))
        view.blit(g2, g2.get_rect(center=(p.x, p.y - 10 * ratio)),
                  special_flags=pygame.BLEND_ADD)


class Building:
    _next_id = 0

    def __init__(self, kind, owner, tx, ty, done=False):
        self.uid = Building._next_id
        Building._next_id += 1
        self.kind = kind
        self.stats = BUILDING_TYPES[kind]
        self.owner = owner
        self.rect = pygame.Rect(tx * TILE, ty * TILE,
                                self.stats["taille"][0] * TILE,
                                self.stats["taille"][1] * TILE)
        self.pos = Vector2(self.rect.center)
        self.max_hp = self.stats["hp"]
        self.done = done
        self.progress = self.stats["build_time"] if done else 0.0
        self.hp = self.max_hp if done else self.max_hp * 0.12
        self.queue = []
        self.prod_t = 0.0
        self.rally = Vector2(self.rect.centerx, self.rect.bottom + 26)
        self.cd = 0.0
        self.attack_target = None
        self.builders = 0
        self.flash = 0.0
        self.open = False
        self.seed = random.random() * 10

    @property
    def sort_y(self):
        return self.rect.bottom

    def can_queue(self, kind, game):
        p = self.owner
        if kind in UPGRADE_TYPES:
            st = UPGRADE_TYPES[kind]
            lvl = p.upgrade_level(kind) + game.pending_upgrades(p, kind)
            return (self.done and len(self.queue) < 5 and p.crystals >= st["cout"]
                    and lvl < st["max"])
        st = UNIT_TYPES[kind]
        return (self.done and len(self.queue) < 5 and p.crystals >= st["cout"]
                and p.supply_used(game) + st["supply"] <= p.supply_cap(game))

    def queue_unit(self, kind, game):
        if self.can_queue(kind, game):
            self.owner.crystals -= prod_stats(kind)["cout"]
            self.queue.append(kind)
            return True
        return False

    def take_damage(self, dmg, game, attacker=None):
        self.hp -= dmg
        self.flash = 0.12
        game.spark(self.pos + Vector2(random.uniform(-14, 14), random.uniform(-14, 14)),
                   (255, 190, 90), 3)
        if self.owner is game.me:
            game.alert_base_attacked()
        if self.hp <= 0:
            game.destroy_building(self)

    def update(self, dt, game):
        self.flash = max(0, self.flash - dt)
        self.cd = max(0, self.cd - dt)
        if not self.done:
            if self.builders > 0:
                rate = 1.0 + 0.55 * (self.builders - 1)
                delta = dt * rate
                self.progress += delta
                self.hp = min(self.max_hp,
                              self.hp + delta / self.stats["build_time"] * self.max_hp * 0.9)
                if random.random() < dt * 6:
                    game.spark(Vector2(random.uniform(self.rect.left, self.rect.right),
                                       random.uniform(self.rect.top, self.rect.bottom)),
                               (210, 205, 170), 2)
                if self.progress >= self.stats["build_time"]:
                    self.done = True
                    self.hp = self.max_hp
                    game.on_building_done(self)
            self.builders = 0
            return
        self.builders = 0
        # la porte s'ouvre uniquement à l'approche d'une unité de son propriétaire
        if self.kind == "porte":
            self.open = any(u.owner is self.owner
                            and dist_point_rect(u.pos, self.rect) < 26
                            for u in game.units)
        # fumée de forge
        if self.kind == "forge" and random.random() < dt * 1.6:
            game.add_particle("smoke", (self.rect.right - 22, self.rect.top - 10),
                              (random.uniform(-4, 4), -20), random.uniform(1.6, 2.6), size=5)
        if self.queue:
            kind = self.queue[0]
            self.prod_t += dt
            if self.prod_t >= prod_stats(kind)["tps"]:
                self.prod_t = 0
                self.queue.pop(0)
                if kind in UPGRADE_TYPES:
                    game.apply_upgrade(self.owner, kind)
                else:
                    game.spawn_unit(kind, self.owner, self.spawn_point(), rally=self.rally)
        if self.stats["degats"] > 0:
            t = self.attack_target
            if t is None or t.hp <= 0 or self.dist_to(t) > self.stats["portee"] + 15:
                self.attack_target = game.find_enemy_near_point(
                    self.pos, self.stats["portee"], self.owner)
            t = self.attack_target
            if t is not None and self.cd <= 0:
                self.cd = self.stats["cooldown"]
                game.fire_projectile(Vector2(self.rect.centerx,
                                             self.rect.top - art.BUILD_EXT + 4),
                                     t, self.stats["degats"], 0,
                                     self.owner, (140, 230, 255))

    def spawn_point(self):
        return Vector2(self.rect.centerx + random.uniform(-18, 18), self.rect.bottom + 14)

    def dist_to(self, ent):
        if isinstance(ent, Building):
            return dist_point_rect(self.pos, ent.rect)
        return dist_point_rect(ent.pos, self.rect)

    # ------------------------------------------------------------- dessin
    def draw(self, view, cam, game):
        r = self.rect.move(-int(cam.x), -int(cam.y))
        if not r.colliderect(pygame.Rect(-160, -160, VIEW_W + 320, VIEW_H + 320)):
            return
        E = art.BUILD_EXT
        skind = "porte_open" if (self.kind == "porte" and self.open) else self.kind
        sprite = art.building_sprite(skind, self.owner.pid)
        sh = art.shadow_tex(int(self.rect.w * 1.15), max(18, self.rect.h // 3))
        view.blit(sh, sh.get_rect(center=(r.centerx + 4, r.bottom - 8)))

        if not self.done:
            pct = self.progress / self.stats["build_time"]
            SH = sprite.get_height()
            cut = max(6, int(SH * pct))
            view.blit(sprite, (r.x, r.bottom - cut), (0, SH - cut, sprite.get_width(), cut))
            # échafaudage
            top = r.bottom - cut - 4
            for x in (r.x + 3, r.right - 5):
                pygame.draw.line(view, (118, 88, 52), (x, r.bottom), (x, top), 3)
                pygame.draw.line(view, (74, 54, 32), (x + 1, r.bottom), (x + 1, top), 1)
            pygame.draw.line(view, (118, 88, 52), (r.x + 3, top), (r.right - 5, top), 2)
            pygame.draw.rect(view, (14, 14, 18), (r.x, r.bottom + 4, r.w, 6))
            pygame.draw.rect(view, C_GOLD, (r.x + 1, r.bottom + 5, int((r.w - 2) * pct), 4))
        else:
            img = sprite
            if self.flash > 0:
                img = art.brightened(sprite)
            view.blit(img, (r.x, r.y - E))
            self.draw_anim(view, r, game)

        if self in game.selection:
            for cx, cy, dx, dy in ((r.x, r.y, 1, 1), (r.right, r.y, -1, 1),
                                   (r.x, r.bottom, 1, -1), (r.right, r.bottom, -1, -1)):
                pygame.draw.line(view, (240, 250, 255), (cx, cy), (cx + 9 * dx, cy), 2)
                pygame.draw.line(view, (240, 250, 255), (cx, cy), (cx, cy + 9 * dy), 2)
            if self.stats["portee"]:
                pygame.draw.circle(view, (150, 220, 250), r.center,
                                   int(self.stats["portee"]), 1)
        if self.hp < self.max_hp or self in game.selection:
            game.draw_hp_bar(view, r.x, r.y - E - 6, r.w, self.hp / self.max_hp)

    def draw_anim(self, view, r, game):
        t = game.time
        if self.kind == "qg":
            pulse = 0.6 + 0.4 * math.sin(t * 2.5 + self.seed)
            g = art.glow((26, 70, 90), 20)
            view.blit(g, g.get_rect(center=(r.centerx, r.y - 14)),
                      special_flags=pygame.BLEND_ADD)
            art.draw_shard(view, r.centerx, r.y - 12, 8, 14 + 2 * pulse, (110, 225, 255))
        elif self.kind == "obelisque":
            cx = r.centerx
            for i, ry in enumerate((-40, -28, -16)):
                pulse = 0.5 + 0.5 * math.sin(t * 3 + i * 1.2 + self.seed)
                g = art.glow((int(20 + 40 * pulse), int(50 + 60 * pulse), 90), 7)
                view.blit(g, g.get_rect(center=(cx, r.bottom + ry)),
                          special_flags=pygame.BLEND_ADD)
            a = t * 1.6 + self.seed
            sx = cx + math.cos(a) * 15
            sy = r.y - 4 + math.sin(t * 2.3 + self.seed) * 5
            art.draw_shard(view, sx, sy, 3, 5, (140, 235, 255))
        elif self.kind == "forge":
            flick = 0.55 + 0.45 * math.sin(t * 11 + self.seed * 7) * math.sin(t * 5.3)
            g = art.glow((int(120 * flick) + 60, int(50 * flick) + 20, 10), 18)
            view.blit(g, g.get_rect(center=(r.centerx, r.bottom - 14)),
                      special_flags=pygame.BLEND_ADD)
        elif self.kind == "tour":
            pulse = 0.6 + 0.4 * math.sin(t * 3.2 + self.seed)
            oc = (r.centerx, r.y - art.BUILD_EXT + 2 + int(math.sin(t * 1.8 + self.seed) * 2))
            g = art.glow((30, 80, 100), int(12 + 4 * pulse))
            view.blit(g, g.get_rect(center=oc), special_flags=pygame.BLEND_ADD)
            pygame.draw.circle(view, (150, 236, 255), oc, 6)
            pygame.draw.circle(view, (230, 252, 255), (oc[0] - 2, oc[1] - 2), 2)


class Unit:
    _next_id = 0

    def __init__(self, kind, owner, pos):
        self.kind = kind
        self.stats = UNIT_TYPES[kind]
        self.owner = owner
        self.pos = Vector2(pos)
        self.hp = self.max_hp = self.stats["hp"]
        self.radius = self.stats["rayon"]
        self.state = "idle"
        self.dest = None
        self.amove = False
        self.amove_dest = None
        self.attack_target = None
        self.auto_target = False
        self.anchor = None
        self.crystal = None
        self.carry = 0
        self.gather_t = 0.0
        self.build_target = None
        self.cd = 0.0
        self.acquire_t = random.uniform(0, 0.35)
        self.facing = Vector2(1, 0)
        self.flash = 0.0
        # pathfinding : chemin courant (liste de waypoints) et détection de blocage
        self.path = None
        self.path_dest = None
        self.stuck_t = 0.0
        self.repath_cd = 0.0
        self._last_pos = Vector2(pos)
        self._intend = 0.0
        self.uid = Unit._next_id
        Unit._next_id += 1

    @property
    def sort_y(self):
        return self.pos.y + self.radius

    # ---------------- ordres
    def order_move(self, dest, amove=False):
        self.state = "move"
        self.dest = Vector2(dest)
        self.path = None
        self.stuck_t = 0.0
        self.amove = amove
        self.amove_dest = Vector2(dest) if amove else None
        self.attack_target = None
        self.auto_target = False
        self.crystal = None if not amove else self.crystal
        self.build_target = None

    def order_attack(self, target, auto=False):
        self.state = "attack"
        self.attack_target = target
        self.auto_target = auto
        if auto and self.anchor is None:
            self.anchor = Vector2(self.pos)
        if not auto:
            self.amove_dest = None
            self.build_target = None

    def order_harvest(self, crystal):
        if self.kind != "ouvrier":
            return
        self.state = "harvest"
        self.crystal = crystal
        self.attack_target = None
        self.build_target = None

    def order_build(self, building):
        if self.kind != "ouvrier":
            return
        self.state = "build"
        self.build_target = building
        self.attack_target = None

    # ---------------- helpers
    def dist_to(self, ent):
        if isinstance(ent, Building):
            return dist_point_rect(self.pos, ent.rect)
        return self.pos.distance_to(ent.pos)

    def step_toward(self, dest, dt, stop=4, game=None):
        """Avance vers `dest`. Suit un chemin A* si la ligne droite est bloquée
        (détection de blocage : le déplacement réel est mesuré d'une frame à
        l'autre dans update(), après la résolution des collisions)."""
        if (dest - self.pos).length() <= stop:
            self.path = None
            return True
        # la cible a bougé : on abandonne le chemin et on repart en ligne droite
        if self.path is not None and (self.path_dest is None
                                      or self.path_dest.distance_to(dest) > TILE * 1.5):
            self.path = None
        if game is not None and self.stuck_t > 0.45 and self.repath_cd <= 0:
            self.stuck_t = 0.0
            self.repath_cd = 1.2
            self.path = game.find_path(self.pos, dest, self.owner)
            self.path_dest = Vector2(dest)
        target = dest
        if self.path:
            while self.path and self.pos.distance_to(self.path[0]) <= TILE * 0.45:
                self.path.pop(0)
            if self.path:
                target = self.path[0]
            else:
                self.path = None
        d = target - self.pos
        L = d.length()
        step = self.stats["vitesse"] * dt
        self._intend = min(step, L)
        if step >= L:
            self.pos.update(target)
            if d.length_squared() > 0:
                self.facing = d.normalize()
            return self.path is None and target == dest
        d.scale_to_length(step)
        self.pos += d
        self.facing = d.normalize()
        return False

    def attack_damage(self):
        return self.stats["degats"] * (1 + 0.15 * self.owner.atk_level)

    def fire_at(self, target, game):
        self.cd = self.stats["cooldown"]
        dmg = self.attack_damage()
        if self.stats["portee"] > 40:
            col = (200, 120, 255) if self.kind == "mage" else self.owner.colors["light"]
            game.fire_projectile(Vector2(self.pos), target, dmg,
                                 self.stats["splash"], self.owner, col,
                                 magic=(self.kind == "mage"),
                                 arrow=(self.kind == "archer"),
                                 siege=(self.kind == "baliste"))
        else:
            target.take_damage(dmg, game, self)
            game.spark(target.pos if not isinstance(target, Building)
                       else Vector2(target.rect.center), (255, 220, 120), 2)
            game.play("hit")

    def take_damage(self, dmg, game, attacker=None):
        dmg *= 1 - 0.12 * self.owner.def_level
        self.hp -= dmg
        self.flash = 0.1
        if (attacker is not None and self.state in ("idle", "move") and not self.amove
                and self.stats["aggro"] > 0 and self.attack_target is None):
            self.order_attack(attacker, auto=True)
        if self.owner is game.me and self.kind == "ouvrier":
            game.alert_base_attacked()
        if self.hp <= 0:
            game.kill_unit(self, attacker)

    # ---------------- update
    def update(self, dt, game):
        st = self.stats
        self.cd = max(0, self.cd - dt)
        self.flash = max(0, self.flash - dt)
        self.acquire_t -= dt
        self.repath_cd = max(0, self.repath_cd - dt)
        # blocage : on voulait avancer la frame passée mais la position n'a
        # presque pas changé (mur, bâtiment posé sur le trajet, embouteillage)
        if self._intend > 1e-4:
            if self.pos.distance_to(self._last_pos) < self._intend * 0.35:
                self.stuck_t += dt
            else:
                self.stuck_t = 0.0
        self._intend = 0.0
        self._last_pos = Vector2(self.pos)

        if self.state == "idle":
            if st["aggro"] > 0 and self.acquire_t <= 0:
                self.acquire_t = 0.35
                tgt = game.find_enemy_near_point(self.pos, st["aggro"], self.owner)
                if tgt is not None:
                    self.order_attack(tgt, auto=True)
            elif self.kind == "ouvrier" and self.carry >= 10:
                self.state = "return"

        elif self.state == "move":
            if self.amove and st["aggro"] > 0 and self.acquire_t <= 0:
                self.acquire_t = 0.35
                tgt = game.find_enemy_near_point(self.pos, st["aggro"], self.owner)
                if tgt is not None:
                    self.order_attack(tgt, auto=True)
                    return
            if self.step_toward(self.dest, dt, game=game):
                self.state = "idle"
                self.amove = False

        elif self.state == "attack":
            t = self.attack_target
            if t is None or t.hp <= 0:
                self.attack_target = None
                if self.amove_dest is not None:
                    self.order_move(self.amove_dest, amove=True)
                elif self.auto_target and self.anchor is not None:
                    a = self.anchor
                    self.anchor = None
                    self.order_move(a)
                else:
                    self.state = "idle"
                return
            d = self.dist_to(t)
            reach = st["portee"] + self.radius + (0 if isinstance(t, Building) else t.radius) * 0.3
            if d <= reach:
                aim = (Vector2(t.rect.center) if isinstance(t, Building) else t.pos)
                v = aim - self.pos
                if v.length_squared() > 0:
                    self.facing = v.normalize()
                if self.cd <= 0:
                    self.fire_at(t, game)
            else:
                aim = (Vector2(t.rect.center) if isinstance(t, Building) else t.pos)
                self.step_toward(aim, dt, stop=reach - 2, game=game)
                if (self.auto_target and self.anchor is not None
                        and self.pos.distance_to(self.anchor) > st["aggro"] * 1.8):
                    a = self.anchor
                    self.anchor = None
                    self.attack_target = None
                    self.order_move(a)

        elif self.state == "harvest":
            c = self.crystal
            if c is None or c.amount <= 0:
                self.crystal = game.nearest_crystal(self.pos)
                if self.crystal is None:
                    self.state = "return" if self.carry else "idle"
                return
            if self.carry >= 10:
                self.state = "return"
                return
            if self.pos.distance_to(c.pos) <= c.radius + self.radius + 5:
                self.gather_t += dt
                if random.random() < dt * 5:
                    game.spark(c.pos + Vector2(random.uniform(-8, 8), random.uniform(-8, 8)),
                               C_CRYSTAL, 1)
                if self.gather_t >= 1.5:
                    self.gather_t = 0
                    got = min(10, c.amount)
                    c.amount -= got
                    self.carry = got
                    self.state = "return"
            else:
                self.step_toward(c.pos, dt, stop=c.radius + self.radius + 3, game=game)

        elif self.state == "return":
            depot = game.nearest_depot(self.pos, self.owner)
            if depot is None:
                self.state = "idle"
                return
            if self.dist_to(depot) <= self.radius + 8:
                gain = int(round(self.carry * self.owner.income_mult))
                self.owner.crystals += gain
                self.owner.total_gathered += gain
                self.carry = 0
                if self.owner is game.me:
                    game.play("depot")
                if self.crystal is not None and self.crystal.amount > 0:
                    self.state = "harvest"
                else:
                    self.crystal = game.nearest_crystal(self.pos)
                    self.state = "harvest" if self.crystal else "idle"
            else:
                self.step_toward(Vector2(depot.rect.center), dt,
                                 stop=self.radius + 6, game=game)

        elif self.state == "build":
            b = self.build_target
            if b is None or b.hp <= 0 or b.done:
                self.build_target = None
                if b is not None and b.done and self.crystal is not None:
                    self.state = "harvest"
                else:
                    self.state = "idle"
                return
            if self.dist_to(b) <= self.radius + 7:
                b.builders += 1
            else:
                self.step_toward(Vector2(b.rect.center), dt,
                                 stop=self.radius + 5, game=game)

    # ---------------- dessin
    def draw(self, view, cam, game):
        p = self.pos - cam
        if not (-40 < p.x < VIEW_W + 40 and -40 < p.y < VIEW_H + 40):
            return
        x, y = int(p.x), int(p.y)
        r = self.radius
        # ombre
        sh = art.shadow_tex(r * 2 + 8, r + 4)
        view.blit(sh, sh.get_rect(center=(x + 2, y + r - 2)))
        if self in game.selection:
            ring = art.sel_ring(r)
            view.blit(ring, ring.get_rect(center=(x, y + r - 2)))
        # sprite orienté
        frames = art.unit_frames(self.kind, self.owner.pid)
        fr = frames[art.frame_index(self.facing)]
        bob = math.sin(game.time * 10 + self.uid) * 1.5 if self.state != "idle" else 0
        off = Vector2(0, 0)
        if self.state == "attack" and self.cd > self.stats["cooldown"] - 0.15:
            k = (self.cd - (self.stats["cooldown"] - 0.15)) / 0.15
            off = self.facing * 5 * k
        if self.flash > 0:
            fr = art.brightened(fr)
        view.blit(fr, fr.get_rect(center=(x + off.x, y - 3 + bob + off.y)))
        # détails dynamiques
        if self.kind == "mage":
            tip = self.pos + self.facing * 11 + Vector2(-self.facing.y, self.facing.x) * -7
            g = art.glow((40, 110, 130), 8)
            view.blit(g, g.get_rect(center=(tip.x - cam.x, tip.y - cam.y - 6)),
                      special_flags=pygame.BLEND_ADD)
        elif self.kind == "golem":
            pulse = 0.5 + 0.5 * math.sin(game.time * 4 + self.uid)
            g = art.glow((int(20 + 40 * pulse), int(40 + 50 * pulse), 70), 9)
            view.blit(g, g.get_rect(center=(x, y - 3)), special_flags=pygame.BLEND_ADD)
        if self.carry:
            ic = art.icon_crystal(12)
            view.blit(ic, (x + 4, y - r - 12))
        if self.hp < self.max_hp or self in game.selection:
            game.draw_hp_bar(view, x - r, y - r - 12, r * 2, self.hp / self.max_hp)


class Projectile:
    def __init__(self, pos, target, dmg, splash, owner, color, magic=False, arrow=False,
                 siege=False):
        self.pos = Vector2(pos)
        self.target = target
        self.dmg = dmg
        self.splash = splash
        self.owner = owner
        self.color = color
        self.magic = magic
        self.arrow = arrow
        self.siege = siege
        self.speed = 300 if magic else (250 if siege else 380)
        self.life = 3.0
        self.dead = False
        self.dir = Vector2(1, 0)

    def target_pos(self):
        if isinstance(self.target, Building):
            return Vector2(self.target.rect.center)
        return Vector2(self.target.pos)

    def update(self, dt, game):
        self.life -= dt
        if self.life <= 0:
            self.dead = True
            return
        if self.target is None or self.target.hp <= 0:
            self.dead = True
            game.spark(self.pos, self.color, 2)
            return
        tp = self.target_pos()
        d = tp - self.pos
        L = d.length()
        step = self.speed * dt
        if L <= step + 6:
            self.dead = True
            dmg = self.dmg
            if self.siege and isinstance(self.target, Building):
                dmg *= 3
            self.target.take_damage(dmg, game)
            game.spark(tp, self.color, 4 if (self.magic or self.siege) else 2)
            if self.magic:
                game.play("magic")
                game.add_particle("glow", tp, (0, 0), 0.2, color=(160, 90, 220), size=26)
                for e in game.enemies_near_point(tp, self.splash, self.owner):
                    if e is not self.target and e.hp > 0:
                        e.take_damage(int(self.dmg * 0.6), game)
                game.ring(tp, self.splash, self.color)
            else:
                game.play("hit")
            return
        d.scale_to_length(step)
        self.dir = d.normalize()
        self.pos += d
        if self.magic and random.random() < dt * 20:
            game.spark(self.pos, (190, 140, 255), 1)

    def draw(self, view, cam):
        p = self.pos - cam
        if self.siege:
            # gros carreau de baliste
            tail = p - self.dir * 13
            pygame.draw.line(view, (96, 66, 40), tail, p, 4)
            pygame.draw.line(view, (150, 112, 70), tail, p, 2)
            pygame.draw.line(view, (225, 228, 235),
                             (p.x, p.y), (p.x + self.dir.x * 5, p.y + self.dir.y * 5), 3)
        elif self.arrow:
            tail = p - self.dir * 9
            pygame.draw.line(view, (150, 112, 70), tail, p, 2)
            pygame.draw.line(view, (230, 230, 235),
                             (p.x, p.y), (p.x + self.dir.x * 3, p.y + self.dir.y * 3), 2)
            pygame.draw.line(view, self.color, tail,
                             (tail.x - self.dir.x * 3, tail.y - self.dir.y * 3), 2)
        elif self.magic:
            g = art.glow((90, 40, 130), 10)
            view.blit(g, g.get_rect(center=p), special_flags=pygame.BLEND_ADD)
            pygame.draw.circle(view, (225, 190, 255), (int(p.x), int(p.y)), 3)
            pygame.draw.circle(view, (255, 255, 255), (int(p.x), int(p.y)), 1)
        else:
            g = art.glow((30, 80, 100), 8)
            view.blit(g, g.get_rect(center=p), special_flags=pygame.BLEND_ADD)
            tail = p - self.dir * 7
            pygame.draw.line(view, self.color, tail, p, 3)
            pygame.draw.circle(view, (240, 252, 255), (int(p.x), int(p.y)), 2)


# ------------------------------------------------------------------------ IA
class AIController:
    def __init__(self, game, player, enemy, diff):
        self.game = game
        self.p = player
        self.enemy = enemy
        self.diff = diff
        self.think_t = random.uniform(0.2, 0.8)
        self.wave_size = diff["wave0"]
        self.attack_mode = False
        self.prod_cd = 0.0

    def my(self, seq):
        return [e for e in seq if e.owner is self.p]

    def update(self, dt):
        g = self.game
        self.prod_cd = max(0, self.prod_cd - dt)
        self.think_t -= dt
        if self.think_t > 0:
            return
        self.think_t = 0.55

        units = self.my(g.units)
        blds = self.my(g.buildings)
        workers = [u for u in units if u.kind == "ouvrier"]
        army = [u for u in units if u.kind != "ouvrier"]
        by_kind = {}
        for b in blds:
            by_kind.setdefault(b.kind, []).append(b)
        qgs = [b for b in by_kind.get("qg", []) if b.done]

        for w in workers:
            if w.state == "idle":
                c = g.nearest_crystal(w.pos)
                if c is not None:
                    w.order_harvest(c)

        target_workers = self.diff["workers"]
        for qg in qgs:
            if len(workers) < target_workers and not qg.queue:
                qg.queue_unit("ouvrier", g)

        self.plan_buildings(blds, by_kind, workers, qgs)

        if self.prod_cd <= 0:
            if self.produce_army(by_kind):
                self.prod_cd = self.diff["prod_pause"]

        self.combat(army, blds)

    def plan_buildings(self, blds, by_kind, workers, qgs):
        g, p = self.game, self.p

        def count(kind):
            return len(by_kind.get(kind, []))

        pending = [b for b in blds if not b.done]
        if len(pending) >= 2:
            self.assign_builders(pending, workers)
            return

        want = None
        supply_left = p.supply_cap(g) - p.supply_used(g)
        t = g.time / self.diff["tempo"]
        if count("caserne") < 1 and len(workers) >= 4:
            want = "caserne"
        elif supply_left <= 4 and p.supply_cap(g) < 90:
            want = "obelisque"
        elif count("tour") < 1 and t > 140:
            want = "tour"
        elif count("archerie") < 1 and t > 170:
            want = "archerie"
        elif count("caserne") < 2 and t > 260:
            want = "caserne"
        elif count("tour") < 3 and t > 300:
            want = "tour"
        elif count("forge") < 1 and t > 330:
            want = "forge"
        elif count("sanctuaire") < 1 and t > 360:
            want = "sanctuaire"
        elif count("qg") < 2 and t > 420 and p.crystals > 550:
            want = "qg"
        elif count("archerie") < 2 and t > 480:
            want = "archerie"

        if want is None or p.crystals < BUILDING_TYPES[want]["cout"]:
            self.assign_builders(pending, workers)
            return

        spot = self.find_spot(want, qgs or blds)
        if spot is None:
            return
        p.crystals -= BUILDING_TYPES[want]["cout"]
        b = Building(want, p, spot[0], spot[1])
        g.buildings.append(b)
        g.block_version += 1
        pending.append(b)
        self.assign_builders(pending, workers)

    def assign_builders(self, pending, workers):
        for b in pending:
            if b.builders == 0 and not any(w.build_target is b for w in workers):
                free = [w for w in workers if w.state in ("idle", "harvest", "return")]
                if free:
                    w = min(free, key=lambda w: w.pos.distance_to(Vector2(b.rect.center)))
                    w.order_build(b)

    def find_spot(self, kind, near_blds):
        g = self.game
        if not near_blds:
            return None
        for _ in range(50):
            base = random.choice(near_blds)
            ang = random.uniform(0, math.tau)
            d = random.uniform(2.2, 8.5) * TILE
            if kind == "tour":
                center = Vector2(WORLD_W / 2, WORLD_H / 2)
                v = center - Vector2(base.rect.center)
                ang = math.atan2(v.y, v.x) + random.uniform(-1.0, 1.0)
                d = random.uniform(3.5, 9) * TILE
            if kind == "qg":
                c = g.richest_far_crystal(self.p)
                if c is not None:
                    bp = c.pos + Vector2(math.cos(ang), math.sin(ang)) * random.uniform(70, 120)
                    tx, ty = int(bp.x // TILE), int(bp.y // TILE)
                    if g.valid_placement(kind, tx, ty):
                        return tx, ty
                    continue
            px = base.rect.centerx + math.cos(ang) * d
            py = base.rect.centery + math.sin(ang) * d
            tx, ty = int(px // TILE), int(py // TILE)
            if g.valid_placement(kind, tx, ty):
                return tx, ty
        return None

    def produce_army(self, by_kind):
        g = self.game
        produced = False
        prefs = {"caserne": ["soldat"], "archerie": ["archer", "archer", "mage"],
                 "forge": ["golem", "golem", "baliste"],
                 "sanctuaire": ["up_atq", "up_def"]}
        for kind, choices in prefs.items():
            for b in by_kind.get(kind, []):
                if b.done and len(b.queue) < 2:
                    if b.queue_unit(random.choice(choices), g):
                        produced = True
        return produced

    def combat(self, army, blds):
        g = self.game
        army_supply = sum(UNIT_TYPES[u.kind]["supply"] for u in army)

        threat = None
        for b in blds:
            e = g.find_enemy_near_point(Vector2(b.rect.center), 280, self.p, units_only=True)
            if e is not None:
                threat = e
                break
        if threat is not None:
            for u in army:
                if u.attack_target is None or u.auto_target:
                    u.order_attack(threat)
            return

        enemy_blds = [b for b in g.buildings if b.owner is self.enemy]
        if not enemy_blds:
            return

        effective_wave = min(self.wave_size, self.diff["wave_max"])
        supply_full = self.p.supply_used(g) >= self.p.supply_cap(g) - 2
        if not self.attack_mode and (army_supply >= effective_wave
                                     or (supply_full and army_supply >= 12)):
            self.attack_mode = True
            g.message(f"{g.enemy_name} lance une offensive !", C_BAD)
            g.play("alert")
        if self.attack_mode:
            if army_supply <= max(2, effective_wave * 0.25):
                self.attack_mode = False
                self.wave_size = min(self.wave_size + self.diff["wave_step"],
                                     self.diff["wave_max"])
                home = blds[0].rect.center if blds else (WORLD_W / 2, WORLD_H / 2)
                for u in army:
                    u.order_move(Vector2(home) + Vector2(random.uniform(-60, 60),
                                                         random.uniform(-60, 60)))
                return
            for u in army:
                if u.state == "idle" or (u.state == "move" and not u.amove):
                    tgt = min(enemy_blds, key=lambda b: u.dist_to(b))
                    u.order_move(Vector2(tgt.rect.center), amove=True)


# ---------------------------------------------------------------------- jeu
class Game:
    def __init__(self, difficulty="normal", p0_ai=False, multiplayer=False, local_pid=0,
                 config=None):
        Unit._next_id = 0
        Building._next_id = 0
        self.config = dict(DEFAULT_CONFIG) if config is None \
            else dict(DEFAULT_CONFIG, **config)
        self.speed = int(clamp(self.config["speed"], 1, 300))
        self.zombies_on = bool(self.config["zombies"])
        set_map_size(self.config["map"])
        self.diff_key = difficulty
        diff = DIFFICULTES[difficulty]
        self.multiplayer = multiplayer
        self.local_pid = local_pid
        if multiplayer:
            self.players = [Player(0, False), Player(1, False)]
        else:
            self.players = [Player(0, p0_ai), Player(1, True, diff["income"])]
        if self.zombies_on:
            self.players.append(Player(ZOMBIE_PID, True))
        self.tombstones = []
        self.zombie_warned = False
        # pathfinding : grille de blocage recalculée quand les bâtiments changent
        self.block_version = 0
        self._block_cache_key = None
        self._block_cache = None
        self.net = None
        self.tick = 0
        self.outbox = []
        self.units = []
        self.buildings = []
        self.crystals = []
        self.doodads = []
        self.projectiles = []
        self.particles = []
        self.rings = []
        self.corpses = []
        self.rubble = []
        self.messages = []
        self.selection = []
        self.groups = {}
        self.cam = Vector2(0, 0)
        self.time = 0.0
        self.winner = None
        self.paused = False
        self.show_help = False
        self.placing = None
        self.drag_start = None
        self.pending_amove = False
        self.mouse = (0, 0)
        self.alert_cd = 0.0
        if multiplayer:
            self.enemy_name = FACTION_NAMES[1 - local_pid]
        else:
            self.enemy_name = random.choice(AI_NAMES)
        self.sounds = {} if (AUTOTEST or SMOKE) else build_sounds()
        self.font = pygame.font.SysFont("segoeui", 15)
        self.font_s = pygame.font.SysFont("segoeui", 12)
        self.font_b = pygame.font.SysFont("georgia", 19, bold=True)
        self.font_h = pygame.font.SysFont("georgia", 44, bold=True)
        self.gen_map()
        self.mini_bg = None
        if multiplayer:
            self.ais = []
        else:
            self.ais = [AIController(self, self.players[1], self.players[0], diff)]
            if p0_ai:
                self.ais.append(AIController(self, self.players[0], self.players[1], diff))
        start = self.start_pos[self.local_pid]
        self.cam = Vector2(clamp(start.x - VIEW_W / 2, 0, WORLD_W - VIEW_W),
                           clamp(start.y - VIEW_H / 2, 0, WORLD_H - VIEW_H))
        # brouillard de guerre (purement visuel : la simulation n'en dépend pas,
        # chaque machine calcule le sien à partir de ses propres unités)
        self.fog_explored = bytearray(MAP_W * MAP_H)
        self.fog_visible = bytearray(MAP_W * MAP_H)
        self.fog_timer = 0.0
        self.fog_version = 0
        self._fog_cache = None
        self._fog_mini = None
        self.update_fog()
        self.message("Détruisez tous les bâtiments de " + self.enemy_name + " !", C_TEXT, 6)
        self.message("F1 : aide et commandes", C_DIM, 6)

    @property
    def me(self):
        return self.players[self.local_pid]

    @property
    def zombie_player(self):
        return self.players[ZOMBIE_PID]

    # ------------------------------------------------------------ carte
    def gen_map(self):
        # les positions sont relatives à MAP_W/MAP_H (taille de map paramétrable)
        self.bg = art.make_terrain(WORLD_W, WORLD_H, TILE)
        base_tiles = [(5, MAP_H - 11), (MAP_W - 9, 6)]
        base_px = [(tx * TILE + 64, ty * TILE + 48) for tx, ty in base_tiles]
        for i, (bx, by) in enumerate(base_px):
            art.bake_plaza(self.bg, bx, by, 118, seed=3 + i)
        art.bake_path(self.bg, base_px[0], base_px[1])

        def cluster(cx, cy, n, amount):
            for i in range(n):
                a = i / n * math.tau + random.uniform(-0.3, 0.3)
                d = random.uniform(30, 75)
                self.crystals.append(Crystal(cx * TILE + math.cos(a) * d,
                                             cy * TILE + math.sin(a) * d,
                                             amount + random.randint(-200, 200)))

        (b0x, b0y), (b1x, b1y) = base_tiles
        cluster(b0x + 8, b0y + 3, 5, 1600)
        cluster(b1x - 4, b1y + 2, 5, 1600)
        cluster(MAP_W * 0.50, MAP_H * 0.50, 6, 2200)
        cluster(MAP_W * 0.22, MAP_H * 0.20, 4, 1800)
        cluster(MAP_W * 0.78, MAP_H * 0.80, 4, 1800)
        cluster(MAP_W * 0.47, MAP_H * 0.86, 3, 1400)
        cluster(MAP_W * 0.53, MAP_H * 0.14, 3, 1400)

        # forêts et rochers (décor bloquant) — densité constante quelle que
        # soit la taille de la carte
        area = MAP_W * MAP_H / (64 * 44)
        rng = random.Random(11)
        def far_enough(x, y, dmin_base=230, dmin_c=70):
            for bx, by in base_px:
                if math.hypot(x - bx, y - by) < dmin_base:
                    return False
            for c in self.crystals:
                if c.pos.distance_to(Vector2(x, y)) < dmin_c:
                    return False
            return True

        for _ in range(int(16 * area)):
            gx, gy = rng.randint(60, WORLD_W - 60), rng.randint(60, WORLD_H - 60)
            if not far_enough(gx, gy):
                continue
            for _ in range(rng.randint(3, 6)):
                x = gx + rng.randint(-70, 70)
                y = gy + rng.randint(-55, 55)
                if 30 < x < WORLD_W - 30 and 30 < y < WORLD_H - 30 and far_enough(x, y):
                    self.doodads.append(Doodad("tree", x, y, rng.randint(0, 99)))
        for _ in range(int(14 * area)):
            x, y = rng.randint(40, WORLD_W - 40), rng.randint(40, WORLD_H - 40)
            if far_enough(x, y, 200, 60):
                self.doodads.append(Doodad("rock", x, y, rng.randint(0, 99)))

        self.start_pos = []
        for pid, (tx, ty) in enumerate(base_tiles):
            b = Building("qg", self.players[pid], tx, ty, done=True)
            self.buildings.append(b)
            self.start_pos.append(Vector2(b.rect.center))
            for _ in range(4):
                u = self.spawn_unit("ouvrier", self.players[pid], b.spawn_point())
                c = self.nearest_crystal(u.pos)
                if c is not None:
                    u.order_harvest(c)

        # mode zombie : quelques rôdeurs dispersés, loin des bases de départ
        if self.zombies_on:
            n = int(clamp(MAP_W * MAP_H // 400, 4, 12))
            placed, tries = 0, 0
            while placed < n and tries < 500:
                tries += 1
                x = random.uniform(80, WORLD_W - 80)
                y = random.uniform(80, WORLD_H - 80)
                if all(math.hypot(x - bx, y - by) > 600 for bx, by in base_px):
                    self.spawn_unit("zombie", self.zombie_player, (x, y))
                    placed += 1

    # ------------------------------------------------------------ services
    def play(self, name):
        s = self.sounds.get(name)
        if s is not None:
            s.play()

    def message(self, txt, color=C_TEXT, dur=4.5):
        self.messages.append([txt, color, dur])
        if len(self.messages) > 5:
            self.messages.pop(0)

    def alert_base_attacked(self):
        if self.alert_cd <= 0 and self.time > 5:
            self.alert_cd = 10
            self.message("⚠ Votre base est attaquée !", C_BAD, 4)
            self.play("alert")

    def add_particle(self, kind, pos, vel, life, color=(255, 255, 255), size=3):
        if len(self.particles) > 700:
            return
        self.particles.append(dict(k=kind, p=Vector2(pos), v=Vector2(vel),
                                   t=life, T=life, c=color, s=size))

    def spark(self, pos, color, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            v = random.uniform(20, 90)
            self.add_particle("spark", pos, (math.cos(a) * v, math.sin(a) * v),
                              random.uniform(0.25, 0.6), color)

    def ring(self, pos, radius, color):
        self.rings.append([Vector2(pos), 6, radius, color])

    def spawn_unit(self, kind, owner, pos, rally=None):
        u = Unit(kind, owner, pos)
        self.units.append(u)
        if rally is not None:
            if kind == "ouvrier":
                c = self.nearest_crystal(Vector2(rally))
                if c is not None and Vector2(rally).distance_to(c.pos) < 200:
                    u.order_harvest(c)
                else:
                    u.order_move(rally)
            else:
                u.order_move(rally, amove=True)
        return u

    def kill_unit(self, unit, attacker=None):
        if unit in self.units:
            self.units.remove(unit)
        unit.hp = min(unit.hp, 0)
        unit.owner.units_lost += 1
        if attacker is not None and hasattr(attacker, "owner"):
            attacker.owner.units_killed += 1
        if unit in self.selection:
            self.selection.remove(unit)
        # cadavre qui s'estompe
        fr = art.unit_frames(unit.kind, unit.owner.pid)[art.frame_index(unit.facing)]
        c = fr.copy()
        c.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
        self.corpses.append([c, Vector2(unit.pos), 6.0, 6.0])
        self.spark(unit.pos, unit.owner.colors["light"], 8)
        self.add_particle("smoke", unit.pos, (0, -14), 1.2, size=5)
        self.play("die")
        # mode zombie : une pierre tombale, puis un zombie (les zombies
        # eux-mêmes ne se relèvent pas)
        if self.zombies_on and unit.kind != "zombie":
            self.tombstones.append([Vector2(unit.pos), TOMB_DELAY])
            if not self.zombie_warned:
                self.zombie_warned = True
                self.message("Une pierre tombale se dresse... les morts reviendront.",
                             C_BAD, 5)

    def destroy_building(self, b):
        if b in self.buildings:
            self.buildings.remove(b)
        self.block_version += 1
        b.hp = min(b.hp, 0)
        if b in self.selection:
            self.selection.remove(b)
        # décombres
        rs = pygame.Surface((b.rect.w, b.rect.h + 10), pygame.SRCALPHA)
        rng = random.Random(b.rect.x)
        pygame.draw.ellipse(rs, (36, 32, 28, 140),
                            (4, b.rect.h // 3, b.rect.w - 8, b.rect.h * 2 // 3))
        for _ in range(b.rect.w // 4):
            x = rng.randint(4, b.rect.w - 5)
            y = rng.randint(b.rect.h // 3, b.rect.h - 2)
            g = rng.randint(60, 110)
            pygame.draw.circle(rs, (g, g - 4, g - 10, 230), (x, y), rng.randint(2, 5))
        self.rubble.append([rs, Vector2(b.rect.topleft), 25.0, 25.0])
        # explosion
        cpos = Vector2(b.rect.center)
        self.add_particle("glow", cpos, (0, 0), 0.22, color=(255, 190, 90), size=44)
        for _ in range(4):
            self.spark(cpos + Vector2(random.uniform(-20, 20), random.uniform(-20, 20)),
                       (255, 160, 70), 6)
        for _ in range(8):
            self.add_particle("smoke",
                              cpos + Vector2(random.uniform(-b.rect.w / 3, b.rect.w / 3),
                                             random.uniform(-b.rect.h / 3, b.rect.h / 3)),
                              (random.uniform(-10, 10), random.uniform(-30, -12)),
                              random.uniform(1.2, 2.2), size=9)
        for _ in range(10):
            self.add_particle("debris", cpos,
                              (random.uniform(-90, 90), random.uniform(-160, -40)),
                              random.uniform(0.5, 1.0), color=(72, 66, 58))
        self.ring(cpos, 46, (255, 170, 80))
        self.play("die")
        if b.owner is self.me:
            self.message(f"Votre {BUILDING_TYPES[b.kind]['nom']} a été détruit !", C_BAD)
        else:
            self.message(f"{BUILDING_TYPES[b.kind]['nom']} ennemi détruit !", C_GOOD)

    def on_building_done(self, b):
        if b.owner is self.me:
            self.message(f"{BUILDING_TYPES[b.kind]['nom']} terminé.", C_GOOD, 3)
            self.play("done")

    def pending_upgrades(self, p, kind):
        return sum(k == kind for b in self.buildings if b.owner is p for k in b.queue)

    def apply_upgrade(self, p, kind):
        if kind == "up_atq":
            p.atk_level += 1
            lvl, label = p.atk_level, "Attaque"
        else:
            p.def_level += 1
            lvl, label = p.def_level, "Défense"
        if p is self.me:
            self.message(f"{label} améliorée (niveau {lvl}/{UPGRADE_TYPES[kind]['max']}) !",
                         C_GOOD, 4)
            self.play("done")

    def fire_projectile(self, pos, target, dmg, splash, owner, color,
                        magic=False, arrow=False, siege=False):
        self.projectiles.append(Projectile(pos, target, dmg, splash, owner, color,
                                           magic, arrow, siege))

    # ------------------------------------------------------- commandes
    # Toute action de joueur passe par une commande sérialisable : en solo
    # elle s'applique immédiatement, en LAN elle est envoyée à l'adversaire
    # et exécutée au même tick sur les deux machines (lockstep).
    def issue(self, cmd):
        cmd["pid"] = self.local_pid
        if self.net is None:
            self.apply_command(cmd)
        else:
            self.outbox.append(cmd)

    def unit_by_id(self, uid):
        for u in self.units:
            if u.uid == uid:
                return u
        return None

    def building_by_id(self, bid):
        for b in self.buildings:
            if b.uid == bid:
                return b
        return None

    def apply_command(self, cmd):
        pid = cmd["pid"]
        p = self.players[pid]
        local = pid == self.local_pid
        op = cmd["op"]
        if op == "order":
            self.exec_order(p, cmd, local)
        elif op == "amove":
            units = [self.unit_by_id(i) for i in cmd["ids"]]
            units = [u for u in units if u is not None and u.owner is p]
            for u in units:
                u.order_move(Vector2(cmd["x"], cmd["y"]), amove=True)
            if units and local:
                self.ring(Vector2(cmd["x"], cmd["y"]), 24, (255, 120, 100))
        elif op == "rally":
            for bid in cmd["ids"]:
                b = self.building_by_id(bid)
                if b is not None and b.owner is p:
                    b.rally = Vector2(cmd["x"], cmd["y"])
            if local:
                self.message("Point de ralliement défini.", C_DIM, 1.5)
        elif op == "place":
            self.exec_place(p, cmd, local)
        elif op == "prod":
            b = self.building_by_id(cmd["bid"])
            if b is not None and b.owner is p and cmd["kind"] in b.stats["prod"]:
                b.queue_unit(cmd["kind"], self)
        elif op == "pause":
            self.paused = not self.paused

    def exec_order(self, p, cmd, local):
        units = [self.unit_by_id(i) for i in cmd["ids"]]
        units = [u for u in units if u is not None and u.owner is p]
        if not units:
            return
        world = Vector2(cmd["x"], cmd["y"])
        ent = self.entity_at(world)
        if isinstance(ent, Crystal):
            for u in units:
                if u.kind == "ouvrier":
                    u.order_harvest(ent)
                else:
                    u.order_move(world)
            if local:
                self.ring(world, 16, C_CRYSTAL)
            return
        if isinstance(ent, (Unit, Building)) and ent.owner is not p:
            for u in units:
                u.order_attack(ent)
            if local:
                self.ring(world, 18, (255, 110, 90))
            return
        if isinstance(ent, Building) and ent.owner is p and not ent.done:
            for u in units:
                if u.kind == "ouvrier":
                    u.order_build(ent)
                else:
                    u.order_move(world)
            return
        n = len(units)
        cols = max(1, int(math.sqrt(n)))
        for i, u in enumerate(units):
            off = Vector2((i % cols - cols / 2 + 0.5) * (u.radius * 2 + 6),
                          (i // cols - n / cols / 2 + 0.5) * (u.radius * 2 + 6))
            u.order_move(world + off)
        if local:
            self.ring(world, 14, (140, 255, 160))

    def exec_place(self, p, cmd, local):
        kind = cmd["kind"]
        tx, ty = cmd["tx"], cmd["ty"]
        if (p.crystals < BUILDING_TYPES[kind]["cout"]
                or not self.valid_placement(kind, tx, ty)):
            if local:
                self.message("Construction impossible.", C_BAD, 2)
            return
        p.crystals -= BUILDING_TYPES[kind]["cout"]
        b = Building(kind, p, tx, ty)
        self.buildings.append(b)
        self.block_version += 1
        for uid in cmd["ids"]:
            u = self.unit_by_id(uid)
            if u is not None and u.owner is p and u.kind == "ouvrier":
                u.order_build(b)

    def state_hash(self):
        """Empreinte de l'état de simulation, pour détecter une désynchro."""
        parts = []
        for u in sorted(self.units, key=lambda u: u.uid):
            parts.append(f"u{u.uid}:{u.pos.x:.3f},{u.pos.y:.3f},{u.hp:.2f},{u.carry}")
        for b in sorted(self.buildings, key=lambda b: b.uid):
            parts.append(f"b{b.uid}:{b.hp:.2f},{b.progress:.2f},{len(b.queue)}")
        for p in self.players:
            parts.append(f"p{p.crystals},{p.atk_level},{p.def_level}")
        for c in self.crystals:
            parts.append(f"c{int(c.amount)}")
        for pos, t in self.tombstones:
            parts.append(f"g{pos.x:.1f},{pos.y:.1f},{t:.2f}")
        return zlib.crc32(";".join(parts).encode())

    # ------------------------------------------------------- pathfinding
    def tile_blocked_map(self, owner):
        """Grille MAP_W×MAP_H des cases occupées par un bâtiment (1 = bloqué).
        Les portes du joueur `owner` sont considérées passantes."""
        key = (self.block_version, owner.pid)
        if self._block_cache_key != key:
            grid = bytearray(MAP_W * MAP_H)
            for b in self.buildings:
                if b.kind == "porte" and b.owner is owner:
                    continue
                tx0 = max(0, b.rect.left // TILE)
                ty0 = max(0, b.rect.top // TILE)
                tx1 = min(MAP_W - 1, (b.rect.right - 1) // TILE)
                ty1 = min(MAP_H - 1, (b.rect.bottom - 1) // TILE)
                for ty in range(ty0, ty1 + 1):
                    row = ty * MAP_W
                    for tx in range(tx0, tx1 + 1):
                        grid[row + tx] = 1
            self._block_cache_key = key
            self._block_cache = grid
        return self._block_cache

    def find_path(self, start, goal, owner):
        """A* 8 directions sur la grille des bâtiments. Renvoie une liste de
        waypoints (centres de cases, but exact en dernier) ou None.
        Si le but est inaccessible, renvoie un chemin vers la case atteignable
        la plus proche (best effort). Déterministe : tie-break par ordre
        d'insertion dans le tas."""
        grid = self.tile_blocked_map(owner)
        sx = int(clamp(start.x // TILE, 0, MAP_W - 1))
        sy = int(clamp(start.y // TILE, 0, MAP_H - 1))
        gx = int(clamp(goal.x // TILE, 0, MAP_W - 1))
        gy = int(clamp(goal.y // TILE, 0, MAP_H - 1))
        if grid[sy * MAP_W + sx]:
            # coincé contre/dans un bâtiment : repartir de la case libre voisine
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = sx + dx, sy + dy
                    if (0 <= nx < MAP_W and 0 <= ny < MAP_H
                            and not grid[ny * MAP_W + nx]):
                        sx, sy = nx, ny
                        break
                else:
                    continue
                break
            else:
                return None

        def h(x, y):
            dx, dy = abs(x - gx), abs(y - gy)
            return max(dx, dy) + 0.41421 * min(dx, dy)

        start_n = (sx, sy)
        open_heap = [(h(sx, sy), 0, start_n)]
        g_cost = {start_n: 0.0}
        came = {}
        best_n, best_h = start_n, h(sx, sy)
        counter = 0
        expansions = 0
        goal_n = (gx, gy)
        reached = False
        while open_heap and expansions < 9000:
            _f, _c, node = heapq.heappop(open_heap)
            if node == goal_n:
                reached = True
                break
            expansions += 1
            x, y = node
            base = g_cost[node]
            for dx, dy, cost in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                                 (1, 1, 1.41421), (1, -1, 1.41421),
                                 (-1, 1, 1.41421), (-1, -1, 1.41421)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                    continue
                if grid[ny * MAP_W + nx]:
                    continue
                # pas de coupe de coin le long d'un bâtiment
                if dx and dy and (grid[y * MAP_W + nx] or grid[ny * MAP_W + x]):
                    continue
                ng = base + cost
                nn = (nx, ny)
                if ng < g_cost.get(nn, 1e18):
                    g_cost[nn] = ng
                    came[nn] = node
                    counter += 1
                    nh = h(nx, ny)
                    if nh < best_h:
                        best_h, best_n = nh, nn
                    heapq.heappush(open_heap, (ng + nh, counter, nn))
        end = goal_n if reached else best_n
        if end == start_n:
            return None
        tiles = [end]
        while tiles[-1] in came:
            tiles.append(came[tiles[-1]])
        tiles.reverse()
        # simplification : on saute les waypoints alignés
        pts = []
        for i, (tx, ty) in enumerate(tiles[1:], 1):
            px, py = tiles[i - 1]
            if pts and i + 1 < len(tiles):
                nx2, ny2 = tiles[i + 1]
                if (tx - px, ty - py) == (nx2 - tx, ny2 - ty):
                    continue
            pts.append(Vector2(tx * TILE + TILE / 2, ty * TILE + TILE / 2))
        if reached:
            pts.append(Vector2(goal))
        return pts or None

    # ------------------------------------------------------- brouillard
    def _reveal(self, vis, px, py, radius_tiles):
        tcx, tcy = px / TILE, py / TILE
        r = radius_tiles
        x0, x1 = max(0, int(tcx - r)), min(MAP_W - 1, int(tcx + r))
        y0, y1 = max(0, int(tcy - r)), min(MAP_H - 1, int(tcy + r))
        r2 = r * r
        for ty in range(y0, y1 + 1):
            dy = ty + 0.5 - tcy
            row = ty * MAP_W
            for tx in range(x0, x1 + 1):
                dx = tx + 0.5 - tcx
                if dx * dx + dy * dy <= r2:
                    vis[row + tx] = 1

    def update_fog(self):
        if AUTOTEST:
            return
        vis = bytearray(MAP_W * MAP_H)
        me = self.me
        for u in self.units:
            if u.owner is me:
                self._reveal(vis, u.pos.x, u.pos.y, 5.5)
        for b in self.buildings:
            if b.owner is me:
                self._reveal(vis, b.rect.centerx, b.rect.centery,
                             8.0 if b.kind == "tour" else 6.5)
        self.fog_visible = vis
        exp = self.fog_explored
        for i, v in enumerate(vis):
            if v:
                exp[i] = 1
        self.fog_version += 1

    def fog_state(self, x, y):
        """0 = inexploré, 1 = exploré mais hors de vue, 2 = visible."""
        tx, ty = int(x // TILE), int(y // TILE)
        if not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
            return 0
        i = ty * MAP_W + tx
        if self.fog_visible[i]:
            return 2
        return 1 if self.fog_explored[i] else 0

    def draw_fog(self, view):
        cam = self.cam
        tx0, ty0 = int(cam.x // TILE), int(cam.y // TILE)
        tw, th = VIEW_W // TILE + 2, VIEW_H // TILE + 2
        key = (tx0, ty0, self.fog_version)
        if self._fog_cache is None or self._fog_cache[0] != key:
            small = pygame.Surface((tw, th), pygame.SRCALPHA)
            for yy in range(th):
                ty = min(ty0 + yy, MAP_H - 1)
                row = ty * MAP_W
                for xx in range(tw):
                    i = row + min(tx0 + xx, MAP_W - 1)
                    if self.fog_visible[i]:
                        continue
                    a = 116 if self.fog_explored[i] else 234
                    small.set_at((xx, yy), (8, 10, 18, a))
            scaled = pygame.transform.smoothscale(small, (tw * TILE, th * TILE))
            self._fog_cache = (key, scaled)
        view.blit(self._fog_cache[1], (tx0 * TILE - cam.x, ty0 * TILE - cam.y))

    # ------------------------------------------------------------ requêtes
    def nearest_crystal(self, pos):
        best, bd = None, 1e18
        for c in self.crystals:
            if c.amount <= 0:
                continue
            d = pos.distance_squared_to(c.pos)
            if d < bd:
                best, bd = c, d
        return best

    def richest_far_crystal(self, player):
        my_qgs = [b for b in self.buildings if b.owner is player and b.kind == "qg"]
        best, score = None, -1
        for c in self.crystals:
            if c.amount < 300:
                continue
            d = min((c.pos.distance_to(Vector2(b.rect.center)) for b in my_qgs), default=0)
            if d > 250 and c.amount + d * 0.3 > score:
                best, score = c, c.amount + d * 0.3
        return best

    def nearest_depot(self, pos, owner):
        best, bd = None, 1e18
        for b in self.buildings:
            if b.owner is owner and b.done and b.stats["depot"]:
                d = dist_point_rect(pos, b.rect) ** 2
                if d < bd:
                    best, bd = b, d
        return best

    def find_enemy_near_point(self, pos, radius, owner, units_only=False):
        best, bd = None, 1e18
        for u in self.units:
            if u.owner is owner or u.hp <= 0:
                continue
            d = pos.distance_to(u.pos)
            if d <= radius and d - 30 < bd:
                best, bd = u, d - 30
        if not units_only:
            for b in self.buildings:
                if b.owner is owner:
                    continue
                d = dist_point_rect(pos, b.rect)
                if d <= radius and d < bd:
                    best, bd = b, d
        return best

    def enemies_near_point(self, pos, radius, owner):
        out = [u for u in self.units
               if u.owner is not owner and pos.distance_to(u.pos) <= radius]
        out += [b for b in self.buildings
                if b.owner is not owner and dist_point_rect(pos, b.rect) <= radius]
        return out

    def entity_at(self, world_pos):
        for u in self.units:
            if world_pos.distance_to(u.pos) <= u.radius + 4:
                return u
        for b in self.buildings:
            if b.rect.collidepoint(world_pos.x, world_pos.y):
                return b
        for c in self.crystals:
            if c.amount > 0 and world_pos.distance_to(c.pos) <= c.radius + 6:
                return c
        return None

    def valid_placement(self, kind, tx, ty):
        tw, th = BUILDING_TYPES[kind]["taille"]
        if tx < 0 or ty < 0 or tx + tw > MAP_W or ty + th > MAP_H:
            return False
        rect = pygame.Rect(tx * TILE, ty * TILE, tw * TILE, th * TILE)
        for b in self.buildings:
            if kind in WALL_KINDS and b.kind in WALL_KINDS:
                # les segments de muraille se posent bord à bord
                if rect.colliderect(b.rect):
                    return False
            elif kind in WALL_KINDS or b.kind in WALL_KINDS:
                if rect.colliderect(b.rect.inflate(8, 8)):
                    return False
            elif rect.colliderect(b.rect.inflate(20, 20)):
                return False
        for c in self.crystals:
            if c.amount > 0 and dist_point_rect(c.pos, rect) < c.radius + 14:
                return False
        for d in self.doodads:
            if dist_point_rect(d.pos, rect) < d.r + 10:
                return False
        return True

    # ------------------------------------------------------------ update
    def update(self, dt):
        if self.paused or self.winner is not None:
            return
        self.time += dt
        self.alert_cd = max(0, self.alert_cd - dt)
        self.fog_timer -= dt
        if self.fog_timer <= 0:
            self.fog_timer = 0.15
            self.update_fog()

        for ai in self.ais:
            ai.update(dt)

        for u in list(self.units):
            u.update(dt, self)
        self.separate_units()
        for b in list(self.buildings):
            b.update(dt, self)
        for pr in self.projectiles:
            pr.update(dt, self)
        self.projectiles = [p for p in self.projectiles if not p.dead]

        for c in list(self.crystals):
            if c.amount <= 0:
                self.spark(c.pos, C_CRYSTAL, 10)
                self.ring(c.pos, 26, C_CRYSTAL)
                self.crystals.remove(c)

        # les pierres tombales éclosent en zombies après TOMB_DELAY
        for t in self.tombstones:
            t[1] -= dt
            if t[1] <= 0:
                self.spawn_unit("zombie", self.zombie_player, t[0])
                self.ring(t[0], 30, (130, 220, 110))
                self.spark(t[0], (140, 230, 120), 6)
        self.tombstones = [t for t in self.tombstones if t[1] > 0]

        # scintillement ambiant des cristaux
        if self.crystals and random.random() < dt * 6:
            c = random.choice(self.crystals)
            self.add_particle("mote",
                              c.pos + Vector2(random.uniform(-10, 10), random.uniform(-6, 4)),
                              (0, -16), random.uniform(0.8, 1.4))

        for p in self.particles:
            p["t"] -= dt
            if p["k"] == "smoke":
                p["v"] *= max(0.0, 1 - 0.8 * dt)
                p["v"].y -= 10 * dt
            elif p["k"] == "debris":
                p["v"].y += 420 * dt
            p["p"] += p["v"] * dt
        self.particles = [p for p in self.particles if p["t"] > 0]

        for r in self.rings:
            r[1] += 140 * dt
        self.rings = [r for r in self.rings if r[1] < r[2] + 20]

        for lst in (self.corpses, self.rubble):
            for c in lst:
                c[2] -= dt
        self.corpses = [c for c in self.corpses if c[2] > 0]
        self.rubble = [c for c in self.rubble if c[2] > 0]

        for m in self.messages:
            m[2] -= dt
        self.messages = [m for m in self.messages if m[2] > 0]

        # seuls les joueurs 0 et 1 comptent (les zombies n'ont pas de bâtiments)
        for pid, p in enumerate(self.players[:2]):
            if not any(b.owner is p for b in self.buildings):
                self.winner = self.players[1 - pid]
                self.play("win" if self.winner is self.me else "lose")
                break

    def separate_units(self):
        cell = 48
        grid = {}
        for u in self.units:
            grid.setdefault((int(u.pos.x // cell), int(u.pos.y // cell)), []).append(u)
        for u in self.units:
            cx, cy = int(u.pos.x // cell), int(u.pos.y // cell)
            for gx in (cx - 1, cx, cx + 1):
                for gy in (cy - 1, cy, cy + 1):
                    for v in grid.get((gx, gy), ()):
                        if v.uid <= u.uid:
                            continue
                        d = u.pos - v.pos
                        L = d.length()
                        m = u.radius + v.radius
                        if 0 < L < m:
                            push = d * ((m - L) / L * 0.5)
                            u.pos += push
                            v.pos -= push
                        elif L == 0:
                            u.pos += Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
            for b in self.buildings:
                if b.kind == "porte" and b.open and b.owner is u.owner:
                    continue
                r = b.rect.inflate(u.radius * 2, u.radius * 2)
                if r.collidepoint(u.pos.x, u.pos.y):
                    dl, dr = u.pos.x - r.left, r.right - u.pos.x
                    dt_, db = u.pos.y - r.top, r.bottom - u.pos.y
                    m = min(dl, dr, dt_, db)
                    if m == dl:
                        u.pos.x = r.left
                    elif m == dr:
                        u.pos.x = r.right
                    elif m == dt_:
                        u.pos.y = r.top
                    else:
                        u.pos.y = r.bottom
            u.pos.x = clamp(u.pos.x, 4, WORLD_W - 4)
            u.pos.y = clamp(u.pos.y, 4, WORLD_H - 4)

    # ------------------------------------------------------------ entrées
    def screen_to_world(self, sx, sy):
        return Vector2(sx + self.cam.x, sy + self.cam.y)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            self.on_key(e)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_mouse_down(e)
        elif e.type == pygame.MOUSEBUTTONUP:
            self.on_mouse_up(e)
        elif e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos

    def on_key(self, e):
        k = e.key
        if k == pygame.K_F1:
            self.show_help = not self.show_help
            return
        if k == pygame.K_p:
            self.issue(dict(op="pause"))
            return
        if k == pygame.K_ESCAPE:
            if self.placing:
                self.placing = None
            elif self.selection:
                self.selection = []
            return
        if pygame.K_1 <= k <= pygame.K_5:
            n = k - pygame.K_0
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                self.groups[n] = [s for s in self.selection if isinstance(s, Unit)]
                self.message(f"Groupe {n} enregistré ({len(self.groups[n])} unités)", C_DIM, 2)
            elif n in self.groups:
                self.groups[n] = [u for u in self.groups[n] if u.hp > 0 and u in self.units]
                if self.groups[n]:
                    self.selection = list(self.groups[n])
            return
        sel_units = [s for s in self.selection if isinstance(s, Unit)
                     and s.owner is self.me]
        sel_blds = [s for s in self.selection if isinstance(s, Building)
                    and s.owner is self.me]
        workers = [u for u in sel_units if u.kind == "ouvrier"]
        if workers and k in BUILD_HOTKEYS.values():
            for kind, key in BUILD_HOTKEYS.items():
                if key == k:
                    self.try_start_placing(kind)
                    return
        if sel_blds:
            b = sel_blds[0]
            for kind, key in PROD_HOTKEYS.items():
                if key == k and kind in b.stats["prod"]:
                    if b.can_queue(kind, self):
                        self.issue(dict(op="prod", bid=b.uid, kind=kind))
                        self.play("click")
                    else:
                        self.deny_prod(b, kind)
                    return
        if k == pygame.K_a and sel_units:
            self.pending_amove = True

    def deny_prod(self, b, kind):
        p = self.me
        st = prod_stats(kind)
        if p.crystals < st["cout"]:
            self.message("Pas assez de cristaux !", C_BAD, 2.5)
        elif kind in UPGRADE_TYPES:
            if p.upgrade_level(kind) + self.pending_upgrades(p, kind) >= st["max"]:
                self.message("Amélioration déjà au niveau maximum.", C_BAD, 2.5)
            elif len(b.queue) >= 5:
                self.message("File de production pleine.", C_BAD, 2)
        elif p.supply_used(self) + st["supply"] > p.supply_cap(self):
            self.message("Ravitaillement insuffisant : construisez un Obélisque (O).", C_BAD, 3)
        elif len(b.queue) >= 5:
            self.message("File de production pleine.", C_BAD, 2)

    def try_start_placing(self, kind):
        p = self.me
        if p.crystals < BUILDING_TYPES[kind]["cout"]:
            self.message("Pas assez de cristaux !", C_BAD, 2.5)
            return
        self.placing = kind
        self.play("click")

    def on_mouse_down(self, e):
        mx, my = e.pos
        if self.winner is not None:
            return
        if e.button in (1, 3) and self.minimap_rect().collidepoint(mx, my):
            wx, wy = self.minimap_to_world(mx, my)
            if e.button == 1:
                self.cam.x = clamp(wx - VIEW_W / 2, 0, WORLD_W - VIEW_W)
                self.cam.y = clamp(wy - VIEW_H / 2, 0, WORLD_H - VIEW_H)
            else:
                self.give_order(Vector2(wx, wy))
            return
        if my >= SCREEN_H - HUD_H:
            if e.button == 1:
                self.click_hud(mx, my)
            return
        if my < TOPBAR_H:
            return
        world = self.screen_to_world(mx, my)
        if e.button == 1:
            if self.placing:
                self.place_building(world)
                return
            if self.pending_amove:
                self.pending_amove = False
                self.amove_order(world)
                return
            self.drag_start = (mx, my)
        elif e.button == 3:
            self.placing = None
            self.pending_amove = False
            self.give_order(world)

    def on_mouse_up(self, e):
        if e.button != 1 or self.drag_start is None:
            return
        x0, y0 = self.drag_start
        x1, y1 = e.pos
        self.drag_start = None
        shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
        if abs(x1 - x0) < 6 and abs(y1 - y0) < 6:
            self.click_select(x1, y1, shift)
        else:
            rect = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            found = [u for u in self.units if u.owner is self.me
                     and rect.collidepoint(u.pos.x - self.cam.x, u.pos.y - self.cam.y)]
            combat = [u for u in found if u.kind != "ouvrier"]
            if combat:
                found = combat
            if shift:
                for u in found:
                    if u not in self.selection:
                        self.selection.append(u)
            elif found:
                self.selection = found

    def click_select(self, sx, sy, shift):
        world = self.screen_to_world(sx, sy)
        ent = self.entity_at(world)
        if isinstance(ent, (Unit, Building)) and ent.owner is self.me:
            if shift and ent in self.selection:
                self.selection.remove(ent)
            elif shift:
                self.selection.append(ent)
            else:
                self.selection = [ent]
            self.play("click")
        elif not shift:
            self.selection = []

    def give_order(self, world):
        sel_units = [s for s in self.selection
                     if isinstance(s, Unit) and s.owner is self.me]
        sel_blds = [s for s in self.selection
                    if isinstance(s, Building) and s.owner is self.me]
        if not sel_units and sel_blds:
            self.issue(dict(op="rally", ids=[b.uid for b in sel_blds],
                            x=world.x, y=world.y))
            return
        if not sel_units:
            return
        self.issue(dict(op="order", ids=[u.uid for u in sel_units],
                        x=world.x, y=world.y))

    def amove_order(self, world):
        sel_units = [s for s in self.selection
                     if isinstance(s, Unit) and s.owner is self.me]
        if sel_units:
            self.issue(dict(op="amove", ids=[u.uid for u in sel_units],
                            x=world.x, y=world.y))

    def place_building(self, world):
        kind = self.placing
        tw, th = BUILDING_TYPES[kind]["taille"]
        tx = int(world.x // TILE) - tw // 2
        ty = int(world.y // TILE) - th // 2
        if not self.valid_placement(kind, tx, ty):
            self.message("Emplacement invalide.", C_BAD, 2)
            return
        if self.me.crystals < BUILDING_TYPES[kind]["cout"]:
            self.message("Pas assez de cristaux !", C_BAD, 2)
            self.placing = None
            return
        workers = [s for s in self.selection
                   if isinstance(s, Unit) and s.kind == "ouvrier" and s.owner is self.me]
        self.issue(dict(op="place", kind=kind, tx=tx, ty=ty,
                        ids=[w.uid for w in workers]))
        self.play("place")
        if not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
            self.placing = None

    # ------------------------------------------------------------ HUD
    def hud_buttons(self):
        btns = []
        p0 = self.me
        sel_blds = [s for s in self.selection if isinstance(s, Building)
                    and s.owner is p0 and s.done]
        sel_workers = [s for s in self.selection if isinstance(s, Unit)
                       and s.kind == "ouvrier" and s.owner is p0]
        x0, y0 = SCREEN_W - 436, SCREEN_H - HUD_H + 34
        bw, bh, gap = 136, 40, 6
        items = []
        if sel_blds:
            b = sel_blds[0]
            for kind in b.stats["prod"]:
                key = pygame.key.name(PROD_HOTKEYS[kind]).upper()
                if kind in UPGRADE_TYPES:
                    st = UPGRADE_TYPES[kind]
                    lvl = p0.upgrade_level(kind)
                    items.append(dict(label=f"{st['nom']} {lvl}/{st['max']}",
                                      sub=f"{st['cout']}  [{key}]",
                                      action=("prod", b, kind), ok=b.can_queue(kind, self),
                                      icon=art.icon_upgrade(kind, 30), desc=st["desc"]))
                else:
                    st = UNIT_TYPES[kind]
                    items.append(dict(label=st["nom"], sub=f"{st['cout']}  [{key}]",
                                      action=("prod", b, kind), ok=b.can_queue(kind, self),
                                      icon=art.icon_unit(kind, self.local_pid, 30),
                                      desc=st["desc"]))
        elif sel_workers:
            for kind in BUILD_MENU:
                st = BUILDING_TYPES[kind]
                key = pygame.key.name(BUILD_HOTKEYS[kind]).upper()
                items.append(dict(label=st["nom"], sub=f"{st['cout']}  [{key}]",
                                  action=("build", kind), ok=p0.crystals >= st["cout"],
                                  icon=art.icon_building(kind, self.local_pid, 28),
                                  desc=st["desc"]))
        for i, it in enumerate(items):
            it["rect"] = pygame.Rect(x0 + (i % 3) * (bw + gap),
                                     y0 + (i // 3) * (bh + gap), bw, bh)
            btns.append(it)
        return btns

    def click_hud(self, mx, my):
        for it in self.hud_buttons():
            if it["rect"].collidepoint(mx, my):
                if not it["ok"]:
                    if it["action"][0] == "prod":
                        self.deny_prod(it["action"][1], it["action"][2])
                    else:
                        self.message("Pas assez de cristaux !", C_BAD, 2)
                    return
                if it["action"][0] == "prod":
                    self.issue(dict(op="prod", bid=it["action"][1].uid,
                                    kind=it["action"][2]))
                    self.play("click")
                else:
                    self.try_start_placing(it["action"][1])
                return
        # icônes de sélection multiple
        for rect, ent in getattr(self, "_sel_rects", []):
            if rect.collidepoint(mx, my):
                self.selection = [ent]
                self.play("click")
                return

    def minimap_rect(self):
        return pygame.Rect(10, SCREEN_H - HUD_H + 12, 210, HUD_H - 24)

    def minimap_to_world(self, mx, my):
        r = self.minimap_rect()
        return ((mx - r.x) / r.w * WORLD_W, (my - r.y) / r.h * WORLD_H)

    def draw_hp_bar(self, surf, x, y, w, pct):
        pct = clamp(pct, 0, 1)
        pygame.draw.rect(surf, (10, 10, 14), (x - 1, y - 1, w + 2, 6))
        pygame.draw.rect(surf, (74, 22, 20), (x, y, w, 4))
        col = C_GOOD if pct > 0.5 else (240, 200, 80) if pct > 0.25 else C_BAD
        fw = int(w * pct)
        if fw > 0:
            pygame.draw.rect(surf, col, (x, y, fw, 4))
            pygame.draw.line(surf, lightc(col, 0.5), (x, y), (x + fw - 1, y))

    def text(self, surf, font, txt, color, x, y, center=False):
        t = font.render(txt, True, color)
        if center:
            x -= t.get_width() // 2
        sh = font.render(txt, True, (10, 12, 16))
        surf.blit(sh, (x + 1, y + 1))
        surf.blit(t, (x, y))
        return t.get_width()

    # ------------------------------------------------------------ dessin
    def draw(self, screen):
        cam = self.cam
        view = screen.subsurface((0, 0, VIEW_W, VIEW_H))
        view.blit(self.bg, (0, 0), (cam.x, cam.y, VIEW_W, VIEW_H))

        # couche sol : décombres et cadavres
        for surf, pos, t, T in self.rubble:
            surf.set_alpha(int(255 * min(1, t / 6)))
            view.blit(surf, (pos.x - cam.x, pos.y - cam.y))
        for surf, pos, t, T in self.corpses:
            surf.set_alpha(int(210 * t / T))
            view.blit(surf, surf.get_rect(center=(pos.x - cam.x, pos.y - cam.y)))
        if self.tombstones:
            ts = art.tombstone_sprite()
            for pos, t in self.tombstones:
                p = pos - cam
                if -30 < p.x < VIEW_W + 30 and -30 < p.y < VIEW_H + 30:
                    view.blit(ts, ts.get_rect(midbottom=(p.x, p.y + 8)))
                    if t < 3.0:  # le zombie arrive : lueur verte qui pulse
                        g = art.glow((40, 90, 30), int(10 + 4 * math.sin(self.time * 9)))
                        view.blit(g, g.get_rect(center=(p.x, p.y)),
                                  special_flags=pygame.BLEND_ADD)

        # entités triées en profondeur (les ennemis cachés par le brouillard
        # ne sont pas dessinés ; les bâtiments restent visibles une fois repérés)
        drawables = []
        drawables.extend(self.crystals)
        drawables.extend(self.doodads)
        for b in self.buildings:
            if b.owner is not self.me \
                    and self.fog_state(b.rect.centerx, b.rect.centery) == 0:
                continue
            drawables.append(b)
        for u in self.units:
            if u.owner is not self.me and self.fog_state(u.pos.x, u.pos.y) < 2:
                continue
            drawables.append(u)
        drawables.sort(key=lambda e: e.sort_y)
        for e in drawables:
            e.draw(view, cam, self)

        # points de ralliement
        for b in self.buildings:
            if b in self.selection and b.done and b.owner is self.me and b.stats["prod"]:
                p = b.rally - cam
                w = math.sin(self.time * 6) * 2
                pygame.draw.line(view, (200, 200, 210), (p.x, p.y), (p.x, p.y - 16), 2)
                pygame.draw.polygon(view, C_GOLD,
                                    [(p.x, p.y - 16), (p.x + 11, p.y - 12 + w), (p.x, p.y - 8)])

        for pr in self.projectiles:
            if pr.owner is not self.me and self.fog_state(pr.pos.x, pr.pos.y) < 2:
                continue
            pr.draw(view, cam)

        # particules
        for p in self.particles:
            sp = p["p"] - cam
            if not (-30 < sp.x < VIEW_W + 30 and -30 < sp.y < VIEW_H + 30):
                continue
            k = p["k"]
            if k == "spark":
                pygame.draw.circle(view, p["c"], (int(sp.x), int(sp.y)),
                                   max(1, int(3 * p["t"] / p["T"])))
            elif k == "smoke":
                size = clamp(int(p["s"] + (1 - p["t"] / p["T"]) * 12), 4, 26)
                tex = art.smoke_tex(size)
                tex.set_alpha(int(190 * p["t"] / p["T"]))
                view.blit(tex, tex.get_rect(center=(sp.x, sp.y)))
            elif k == "glow":
                g = art.glow(p["c"], p["s"])
                view.blit(g, g.get_rect(center=(sp.x, sp.y)),
                          special_flags=pygame.BLEND_ADD)
            elif k == "debris":
                pygame.draw.rect(view, p["c"], (int(sp.x), int(sp.y), 3, 3))
            elif k == "mote":
                g = art.glow((30, 80, 100), 4)
                view.blit(g, g.get_rect(center=(sp.x, sp.y)),
                          special_flags=pygame.BLEND_ADD)

        for pos, r, rmax, col in self.rings:
            sp = pos - cam
            f = max(0.0, 1 - r / (rmax + 20))
            pygame.draw.circle(view, shade(col, f), (int(sp.x), int(sp.y)), int(r), 2)

        self.draw_fog(view)

        # fantôme de placement
        if self.placing and self.mouse[1] < VIEW_H:
            world = self.screen_to_world(*self.mouse)
            kind = self.placing
            tw, th = BUILDING_TYPES[kind]["taille"]
            tx = int(world.x // TILE) - tw // 2
            ty = int(world.y // TILE) - th // 2
            ok = self.valid_placement(kind, tx, ty)
            r = pygame.Rect(tx * TILE - cam.x, ty * TILE - cam.y, tw * TILE, th * TILE)
            ghost = art.building_sprite(kind, self.local_pid).copy()
            ghost.set_alpha(150)
            view.blit(ghost, (r.x, r.y - art.BUILD_EXT))
            s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            s.fill((90, 220, 120, 70) if ok else (230, 80, 70, 90))
            view.blit(s, r.topleft)
            pygame.draw.rect(view, C_GOOD if ok else C_BAD, r, 2)
            if kind == "tour":
                pygame.draw.circle(view, (200, 240, 255), r.center,
                                   int(BUILDING_TYPES["tour"]["portee"]), 1)

        if self.drag_start is not None:
            x0, y0 = self.drag_start
            x1, y1 = self.mouse
            r = pygame.Rect(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
            s = pygame.Surface((max(1, r.w), max(1, r.h)), pygame.SRCALPHA)
            s.fill((140, 255, 170, 30))
            view.blit(s, r.topleft)
            pygame.draw.rect(view, (170, 255, 190), r, 1)

        view.blit(art.vignette(VIEW_W, VIEW_H), (0, 0))

        self.draw_topbar(screen)
        self.draw_messages(screen)
        self.draw_hud(screen)
        if self.show_help:
            self.draw_help(screen)
        if self.paused and self.winner is None:
            self.text(screen, self.font_h, "PAUSE", C_TEXT, SCREEN_W // 2,
                      VIEW_H // 2 - 40, center=True)
        if self.winner is not None:
            self.draw_end(screen)

    def draw_topbar(self, screen):
        screen.blit(art.panel_img(SCREEN_W, TOPBAR_H, gems=False), (0, 0))
        p0 = self.me
        screen.blit(art.icon_crystal(20), (12, 5))
        self.text(screen, self.font, f"{p0.crystals}", C_TEXT, 38, 4)
        used, cap = p0.supply_used(self), p0.supply_cap(self)
        screen.blit(art.icon_supply(18), (128, 6))
        self.text(screen, self.font, f"{used}/{cap}",
                  C_BAD if used >= cap else C_TEXT, 152, 4)
        mins, secs = divmod(int(self.time), 60)
        self.text(screen, self.font, f"{mins:02d}:{secs:02d}", C_DIM, SCREEN_W // 2, 4,
                  center=True)
        if self.multiplayer:
            t = f"vs {self.enemy_name}  (LAN)"
        else:
            t = f"vs {self.enemy_name}  ({DIFFICULTES[self.diff_key]['nom']})"
        if self.speed > 1:
            t += f"  ·  ralenti ×{self.speed}"
        w = self.font.render(t, True, C_DIM).get_width()
        self.text(screen, self.font, t,
                  PLAYER_COLORS[1 - self.local_pid]["light"], SCREEN_W - w - 12, 4)

    def draw_messages(self, screen):
        y = TOPBAR_H + 8
        for txt, col, dur in self.messages:
            surf = self.font.render(txt, True, col)
            a = int(255 * clamp(dur / 1.0, 0, 1))
            pill = pygame.Surface((surf.get_width() + 18, 22), pygame.SRCALPHA)
            pygame.draw.rect(pill, (12, 14, 22, min(160, a)),
                             pill.get_rect(), border_radius=10)
            pill.blit(surf, (9, 2))
            pill.set_alpha(a)
            screen.blit(pill, (SCREEN_W / 2 - pill.get_width() / 2, y))
            y += 24

    def draw_hud(self, screen):
        screen.blit(art.panel_img(SCREEN_W, HUD_H), (0, SCREEN_H - HUD_H))
        self.draw_minimap(screen)
        x0 = 246
        y0 = SCREEN_H - HUD_H + 14
        self._sel_rects = []

        if len(self.selection) == 1:
            s = self.selection[0]
            # portrait
            pr = pygame.Rect(x0, y0, 74, 74)
            pygame.draw.rect(screen, (16, 18, 26), pr)
            pygame.draw.rect(screen, (96, 108, 132), pr, 1)
            if isinstance(s, Building):
                ic = art.icon_building(s.kind, s.owner.pid, 64)
            else:
                ic = art.icon_unit(s.kind, s.owner.pid, 60)
            screen.blit(ic, ic.get_rect(center=pr.center))
            tx = x0 + 88
            if isinstance(s, Building):
                st = BUILDING_TYPES[s.kind]
                name = st["nom"] + ("" if s.done else "  (chantier)")
                self.text(screen, self.font_b, name, C_TEXT, tx, y0 - 2)
                self.text(screen, self.font, f"PV {int(s.hp)}/{s.max_hp}", C_DIM, tx, y0 + 24)
                self.text(screen, self.font_s, st["desc"], C_DIM, tx, y0 + 46)
                if s.queue:
                    kind = s.queue[0]
                    pst = prod_stats(kind)
                    pct = s.prod_t / pst["tps"]
                    label = ("Recherche : " if kind in UPGRADE_TYPES
                             else "Production : ") + pst["nom"]
                    if len(s.queue) > 1:
                        label += f"  (+{len(s.queue) - 1} en file)"
                    self.text(screen, self.font, label, C_TEXT, tx, y0 + 68)
                    pygame.draw.rect(screen, (14, 16, 22), (tx, y0 + 92, 240, 12))
                    pygame.draw.rect(screen, (40, 150, 200), (tx + 1, y0 + 93,
                                                              int(238 * pct), 10))
                    pygame.draw.rect(screen, (96, 108, 132), (tx, y0 + 92, 240, 12), 1)
                elif not s.done:
                    pct = s.progress / st["build_time"]
                    pygame.draw.rect(screen, (14, 16, 22), (tx, y0 + 92, 240, 12))
                    pygame.draw.rect(screen, C_GOLD, (tx + 1, y0 + 93, int(238 * pct), 10))
                    pygame.draw.rect(screen, (96, 108, 132), (tx, y0 + 92, 240, 12), 1)
                    if s.builders == 0:
                        self.text(screen, self.font_s,
                                  "Aucun ouvrier ! Clic droit avec un ouvrier pour reprendre.",
                                  C_BAD, tx, y0 + 68)
            else:
                st = UNIT_TYPES[s.kind]
                self.text(screen, self.font_b, st["nom"], C_TEXT, tx, y0 - 2)
                self.text(screen, self.font, f"PV {int(s.hp)}/{s.max_hp}", C_DIM, tx, y0 + 24)
                self.text(screen, self.font_s,
                          f"Dégâts {st['degats']}   Portée {st['portee']}   Vitesse {st['vitesse']}",
                          C_DIM, tx, y0 + 46)
                self.text(screen, self.font_s, st["desc"], C_DIM, tx, y0 + 64)
            self.draw_hp_bar(screen, pr.x, pr.bottom + 6, pr.w,
                             s.hp / s.max_hp)
        elif self.selection:
            self.text(screen, self.font_b, f"{len(self.selection)} unités", C_TEXT, x0, y0 - 2)
            gx, gy = x0, y0 + 28
            for i, s in enumerate(self.selection[:16]):
                if not isinstance(s, Unit):
                    continue
                r = pygame.Rect(gx + (i % 8) * 40, gy + (i // 8) * 48, 36, 36)
                pygame.draw.rect(screen, (16, 18, 26), r)
                pygame.draw.rect(screen, (96, 108, 132), r, 1)
                ic = art.icon_unit(s.kind, s.owner.pid, 30)
                screen.blit(ic, ic.get_rect(center=r.center))
                self.draw_hp_bar(screen, r.x + 2, r.bottom - 5, r.w - 4, s.hp / s.max_hp)
                self._sel_rects.append((r, s))
        else:
            self.text(screen, self.font, "Aucune sélection", C_DIM, x0, y0)
            self.text(screen, self.font_s,
                      "Clic gauche : sélectionner    Clic droit : ordre    F1 : aide",
                      C_DIM, x0, y0 + 24)

        # boutons contextuels + infobulle
        hover = None
        for it in self.hud_buttons():
            r = it["rect"]
            state = 2 if not it["ok"] else (1 if r.collidepoint(self.mouse) else 0)
            screen.blit(art.button_img(r.w, r.h, state), r.topleft)
            ic = it["icon"]
            screen.blit(ic, ic.get_rect(center=(r.x + 20, r.centery)))
            c1 = C_TEXT if it["ok"] else C_DIM
            self.text(screen, self.font_s, it["label"], c1, r.x + 40, r.y + 4)
            screen.blit(art.icon_crystal(12), (r.x + 40, r.y + 21))
            self.text(screen, self.font_s, it["sub"], C_CRYSTAL if it["ok"] else C_DIM,
                      r.x + 54, r.y + 20)
            if state == 1:
                hover = it
        sel_workers = any(isinstance(s, Unit) and s.kind == "ouvrier"
                          for s in self.selection)
        if sel_workers or any(isinstance(s, Building) for s in self.selection):
            self.text(screen, self.font_s,
                      "Construire" if sel_workers else "Produire", C_DIM,
                      SCREEN_W - 436, SCREEN_H - HUD_H + 16)
        if hover is not None:
            tip = self.font_s.render(hover["desc"], True, C_TEXT)
            tw = tip.get_width() + 16
            tr = pygame.Rect(SCREEN_W - 12 - tw, SCREEN_H - HUD_H - 30, tw, 24)
            pygame.draw.rect(screen, (14, 16, 24), tr, border_radius=5)
            pygame.draw.rect(screen, (96, 108, 132), tr, 1, border_radius=5)
            screen.blit(tip, (tr.x + 8, tr.y + 4))

    def draw_minimap(self, screen):
        r = self.minimap_rect()
        if self.mini_bg is None:
            self.mini_bg = pygame.transform.smoothscale(self.bg, (r.w, r.h))
        screen.blit(self.mini_bg, r.topleft)
        sx, sy = r.w / WORLD_W, r.h / WORLD_H
        for c in self.crystals:
            pygame.draw.circle(screen, C_CRYSTAL,
                               (int(r.x + c.pos.x * sx), int(r.y + c.pos.y * sy)), 2)
        for b in self.buildings:
            if b.owner is not self.me \
                    and self.fog_state(b.rect.centerx, b.rect.centery) == 0:
                continue
            pygame.draw.rect(screen, b.owner.colors["main"],
                             (r.x + b.rect.x * sx, r.y + b.rect.y * sy,
                              max(3, b.rect.w * sx), max(3, b.rect.h * sy)))
        for u in self.units:
            if u.owner is not self.me and self.fog_state(u.pos.x, u.pos.y) < 2:
                continue
            screen.set_at((int(r.x + u.pos.x * sx), int(r.y + u.pos.y * sy)),
                          u.owner.colors["light"])
        # voile de brouillard sur la minimap
        if self._fog_mini is None or self._fog_mini[0] != self.fog_version:
            small = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
            for ty in range(MAP_H):
                row = ty * MAP_W
                for tx in range(MAP_W):
                    i = row + tx
                    if self.fog_visible[i]:
                        continue
                    a = 116 if self.fog_explored[i] else 220
                    small.set_at((tx, ty), (8, 10, 18, a))
            self._fog_mini = (self.fog_version,
                              pygame.transform.smoothscale(small, (r.w, r.h)))
        screen.blit(self._fog_mini[1], r.topleft)
        cam_r = pygame.Rect(r.x + self.cam.x * sx, r.y + self.cam.y * sy,
                            VIEW_W * sx, VIEW_H * sy)
        pygame.draw.rect(screen, (235, 235, 240), cam_r, 1)
        pygame.draw.rect(screen, (10, 12, 16), r, 2)
        pygame.draw.rect(screen, (96, 108, 132), r.inflate(2, 2), 1)

    def draw_help(self, screen):
        w, h = 640, 480
        r = pygame.Rect(SCREEN_W / 2 - w / 2, VIEW_H / 2 - h / 2, w, h)
        screen.blit(art.panel_img(w, h), r.topleft)
        lines = [
            ("COMMANDES", C_CRYSTAL),
            ("Clic gauche / glisser : sélectionner", C_TEXT),
            ("Clic droit : déplacer / attaquer / récolter / reprendre un chantier", C_TEXT),
            ("A puis clic : attaque-déplacement (l'armée engage tout sur le chemin)", C_TEXT),
            ("Ctrl+1..5 : enregistrer un groupe    1..5 : rappeler le groupe", C_TEXT),
            ("Flèches ou bord de l'écran : caméra    Minimap : clic gauche/droit", C_TEXT),
            ("P : pause    F11 : plein écran    Échap : annuler    F1 : fermer l'aide",
             C_TEXT),
            ("", C_TEXT),
            ("ÉCONOMIE", C_CRYSTAL),
            ("Les ouvriers récoltent les cristaux et les déposent au QG.", C_TEXT),
            ("Ouvrier sélectionné : boutons ou touches pour bâtir (O = Obélisque...).", C_TEXT),
            ("Les Obélisques augmentent le ravitaillement (limite d'unités).", C_TEXT),
            ("", C_TEXT),
            ("ARMÉE", C_CRYSTAL),
            ("Caserne → Soldat [S]    Archerie → Archer [A], Mage [M]", C_TEXT),
            ("Forge → Golem [G], Baliste [B] (dégâts x3 sur les bâtiments)", C_TEXT),
            ("Tour de cristal : défense automatique", C_TEXT),
            ("Sanctuaire : améliore l'Attaque [A] et la Défense [D] (3 niveaux)", C_TEXT),
            ("Muraille [M] / Porte [E] : la porte ne s'ouvre que pour vos unités", C_TEXT),
            ("", C_TEXT),
            ("Détruisez TOUS les bâtiments ennemis pour gagner !", C_GOLD),
        ]
        y = r.y + 18
        for txt, col in lines:
            f = self.font_b if col == C_CRYSTAL else self.font
            self.text(screen, f, txt, col, r.x + 26, y)
            y += 27 if col == C_CRYSTAL else 21

    def draw_end(self, screen):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        s.fill((8, 10, 16, 195))
        screen.blit(s, (0, 0))
        win = self.winner is self.me
        txt = "VICTOIRE !" if win else "DÉFAITE..."
        col = (130, 235, 150) if win else (245, 105, 92)
        t = self.font_h.render(txt, True, col)
        for off in (3, 2):
            g = pygame.transform.smoothscale(
                t, (t.get_width() + off * 14, t.get_height() + off * 8))
            screen.blit(g, g.get_rect(center=(SCREEN_W / 2, 225)),
                        special_flags=pygame.BLEND_ADD)
        screen.blit(t, t.get_rect(center=(SCREEN_W / 2, 225)))
        sub = ("La base de " + self.enemy_name + " est en ruines."
               if win else self.enemy_name + " a rasé votre base.")
        self.text(screen, self.font_b, sub, C_TEXT, SCREEN_W // 2, 268, center=True)
        p0, p1 = self.me, self.players[1 - self.local_pid]
        mins, secs = divmod(int(self.time), 60)
        stats = [
            f"Durée : {mins:02d}:{secs:02d}",
            f"Cristaux récoltés : {p0.total_gathered}   (ennemi : {p1.total_gathered})",
            f"Unités éliminées : {p0.units_killed}   Unités perdues : {p0.units_lost}",
        ]
        y = 330
        for line in stats:
            self.text(screen, self.font, line, C_DIM, SCREEN_W // 2, y, center=True)
            y += 26
        hint = ("Échap : retour au menu" if self.multiplayer
                else "R : rejouer      Échap : quitter")
        self.text(screen, self.font_b, hint, C_TEXT, SCREEN_W // 2, y + 30, center=True)

    def scroll(self, dt, keys):
        dx = dy = 0
        mx, my = self.mouse
        if keys[pygame.K_LEFT] or (0 <= mx < EDGE_SCROLL):
            dx = -1
        if keys[pygame.K_RIGHT] or (mx > SCREEN_W - EDGE_SCROLL):
            dx = 1
        if keys[pygame.K_UP] or (0 <= my < EDGE_SCROLL):
            dy = -1
        if keys[pygame.K_DOWN] or (SCREEN_H - HUD_H - EDGE_SCROLL < my < SCREEN_H - HUD_H):
            dy = 1
        self.cam.x = clamp(self.cam.x + dx * CAM_SPEED * dt, 0, WORLD_W - VIEW_W)
        self.cam.y = clamp(self.cam.y + dy * CAM_SPEED * dt, 0, WORLD_H - VIEW_H)


def global_key(e):
    """Touches globales, valables dans tous les écrans.
    F11 : bascule plein écran. Renvoie True si l'événement est consommé."""
    if e.type == pygame.KEYDOWN and e.key == pygame.K_F11 and not (AUTOTEST or SMOKE):
        pygame.display.toggle_fullscreen()
        return True
    return False


# ---------------------------------------------------------------------- menu
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

    def button(self, screen, r, label, desc=""):
        hov = r.collidepoint(pygame.mouse.get_pos())
        screen.blit(art.button_img(r.w, r.h, 1 if hov else 0), r.topleft)
        lab = self.font_b.render(label, True, (236, 240, 248))
        if desc:
            screen.blit(lab, lab.get_rect(center=(r.centerx, r.y + 20)))
            d = self.font_s.render(desc, True, (150, 158, 174))
            screen.blit(d, d.get_rect(center=(r.centerx, r.y + 44)))
        else:
            screen.blit(lab, lab.get_rect(center=r.center))
        return hov

    def line(self, screen, txt, y, color=(200, 208, 222), big=False, center=True):
        f = self.font_b if big else self.font
        s = f.render(txt, True, color)
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


def game_options(screen, clock, ui, subtitle="Options de la partie"):
    """Écran d'options à la création de partie : renvoie un dict config
    (voir DEFAULT_CONFIG) ou None (retour)."""
    if SMOKE:
        return dict(DEFAULT_CONFIG)
    cfg = dict(DEFAULT_CONFIG)
    cx = SCREEN_W / 2
    bar = pygame.Rect(cx - 160, 384, 320, 12)
    zrow = pygame.Rect(cx - 160, 432, 320, 26)
    map_btns = [(pygame.Rect(cx - 160 + i * 110, 512, 100, 42), key)
                for i, key in enumerate(("petite", "moyenne", "grande"))]
    play = pygame.Rect(cx - 160, 586, 320, 56)
    dragging = False

    def set_speed(mx):
        cfg["speed"] = int(round(1 + clamp((mx - bar.x) / bar.w, 0, 1) * 299))

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
                else:
                    for r, key in map_btns:
                        if r.collidepoint(e.pos):
                            cfg["map"] = key
            if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                dragging = False
            if e.type == pygame.MOUSEMOTION and dragging:
                set_speed(e.pos[0])

        ui.frame(screen, dt, subtitle)
        # --- vitesse (ralenti ×1 à ×300)
        sp = cfg["speed"]
        label = "vitesse normale" if sp == 1 else f"ralenti ×{sp}"
        ui.line(screen, f"Vitesse de jeu : {label}", 352, (226, 230, 238), big=True)
        pygame.draw.rect(screen, (16, 18, 26), bar)
        k = (sp - 1) / 299
        pygame.draw.rect(screen, (40, 120, 170), (bar.x, bar.y, int(bar.w * k), bar.h))
        pygame.draw.rect(screen, (96, 108, 132), bar, 1)
        hx = bar.x + int(bar.w * k)
        pygame.draw.circle(screen, (200, 236, 255), (hx, bar.centery), 9)
        pygame.draw.circle(screen, (30, 60, 80), (hx, bar.centery), 9, 2)
        # --- mode zombie
        box = pygame.Rect(zrow.x, zrow.y + 2, 22, 22)
        pygame.draw.rect(screen, (16, 18, 26), box)
        pygame.draw.rect(screen, (96, 108, 132), box, 1)
        if cfg["zombies"]:
            pygame.draw.lines(screen, (130, 230, 120), False,
                              [(box.x + 4, box.y + 11), (box.x + 9, box.y + 16),
                               (box.x + 18, box.y + 5)], 3)
        s = ui.font.render("Mode zombie : les unités mortes se relèvent", True,
                           (200, 208, 222))
        screen.blit(s, (box.right + 12, zrow.y + 4))
        # --- taille de la carte
        ui.line(screen, "Taille de la carte :", 486, (200, 208, 222))
        for r, key in map_btns:
            ui.button(screen, r, MAP_SIZES[key][0])
            if key == cfg["map"]:
                pygame.draw.rect(screen, (110, 220, 255), r, 2, border_radius=5)
        # --- lancer
        ui.button(screen, play, "Jouer", "Entrée pour lancer la partie")
        pygame.display.flip()


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


# ---------------------------------------------------------------------- main
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
            p0, p1 = game.players
            print(f"t={steps // 20}s  crist={p0.crystals}/{p1.crystals}  "
                  f"unités={sum(u.owner is p0 for u in game.units)}/"
                  f"{sum(u.owner is p1 for u in game.units)}  "
                  f"bât={sum(b.owner is p0 for b in game.buildings)}/"
                  f"{sum(b.owner is p1 for b in game.buildings)}")
    if game.winner is None:
        print("AUTOTEST: pas de vainqueur en 45 min simulées")
    else:
        print(f"AUTOTEST OK — vainqueur : joueur {game.winner.pid} "
              f"({FACTION_NAMES[game.winner.pid]}) à t={int(game.time)}s")
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
    pygame.display.set_caption("CRISTALIS — La Guerre des Cristaux")
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
            cfg = game_options(screen, clock, ui, "Options de la partie (hôte)")
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
