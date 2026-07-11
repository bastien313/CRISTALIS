# -*- coding: utf-8 -*-
"""
CRISTALIS — la classe Game : état de la partie, simulation, commandes
(lockstep), pathfinding, brouillard et entrées joueur. Le rendu est dans
render.RenderMixin.

Invariants lockstep : toute action de joueur passe par issue()/apply_command(),
la simulation ne consomme le RNG global que de façon identique des deux côtés,
et le brouillard reste local (jamais dans state_hash).
"""

import heapq
import json
import math
import os
import random
import time
import zlib

import pygame
from pygame.math import Vector2

import art
from art import clamp
from data import (AI_NAMES, AUTOTEST, BUILD_HOTKEYS, BUILDING_TYPES, C_BAD,
                  C_CRYSTAL, C_DIM, C_GOOD, C_TEXT, DEFAULT_CONFIG, DIFFICULTES,
                  EDGE_SCROLL, CAM_SPEED, FACTION_NAMES, HUD_H, MAP_SIZES,
                  MAX_PLAYERS, PROD_HOTKEYS, SCREEN_H, SCREEN_W, SMOKE, TILE,
                  TOMB_DELAY, TOPBAR_H, UPGRADE_TYPES, VIEW_H, VIEW_W,
                  WALL_KINDS, ZOMBIE_PID, ZOMBIE_TEAM, dist_point_rect,
                  prod_stats)
from entities import Building, Crystal, Doodad, Player, Projectile, Unit
from ia import AIController
from render import RenderMixin


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


def sanitize_config(config):
    """Complète et borne une config de partie (elle peut venir du réseau)."""
    cfg = dict(DEFAULT_CONFIG) if config is None else dict(DEFAULT_CONFIG, **config)
    cfg["speed"] = int(clamp(cfg.get("speed", 1), 1, 300))
    cfg["zombies"] = bool(cfg.get("zombies"))
    cfg["zombie_spawn_interval"] = int(clamp(cfg.get("zombie_spawn_interval", 60), 5, 120))
    cfg["zombie_invasion_delay"] = int(clamp(cfg.get("zombie_invasion_delay", 120), 0, 600))
    if cfg.get("map") not in MAP_SIZES:
        cfg["map"] = "moyenne"
    slots = []
    for i, s in enumerate(list(cfg.get("players") or [])[:MAX_PLAYERS]):
        slots.append(dict(ai=bool(s.get("ai", True)),
                          team=int(clamp(s.get("team", i + 1), 1, MAX_PLAYERS))))
    while len(slots) < 2:
        slots.append(dict(ai=True, team=len(slots) + 1))
    cfg["players"] = slots
    return cfg


# ---------------------------------------------------------------------- jeu
class Game(RenderMixin):
    def __init__(self, difficulty="normal", p0_ai=False, multiplayer=False, local_pid=0,
                 config=None):
        Unit._next_id = 0
        Building._next_id = 0
        self.config = sanitize_config(config)
        self.survival_mode = difficulty == "survie"
        if self.survival_mode:
            self.config["speed"] = 1
            self.config["zombies"] = True
            self.config["players"] = [dict(ai=False, team=1)]
        self.speed = self.config["speed"]
        self.zombies_on = self.config["zombies"]
        _nom, self.map_w, self.map_h, _cap = MAP_SIZES[self.config["map"]]
        self.world_w, self.world_h = self.map_w * TILE, self.map_h * TILE
        self.diff_key = difficulty
        diff = DIFFICULTES[difficulty]
        self.multiplayer = multiplayer
        self.local_pid = local_pid
        # joueurs : un par slot de la config ; en LAN les slots 0/1 sont humains
        self.players = []
        for i, sl in enumerate(self.config["players"]):
            ai = bool(sl["ai"]) or (p0_ai and i == 0)
            if multiplayer and i < 2:
                ai = False
            self.players.append(Player(i, ai, diff["income"] if ai else 1.0,
                                       team=sl["team"]))
        self.zombie_p = None
        if self.zombies_on:
            self.zombie_p = Player(ZOMBIE_PID, True, team=ZOMBIE_TEAM)
            self.players.append(self.zombie_p)
        self.tombstones = []
        self.zombie_warned = False
        self.eliminated = set()
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
        self._group_tap = (0, -10.0)  # double-appui sur un groupe (local)
        self.cam = Vector2(0, 0)
        self.time = 0.0
        self.winner = None
        self.paused = False
        self.show_help = False
        self.placing = None
        self.drag_start = None
        self.pending_amove = False
        self.mouse = (0, 0)
        self.request_return_menu = False
        self.alert_cd = 0.0
        if multiplayer and len(self.combatants) == 2:
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
        # les IA tournent aussi en LAN : elles sont déterministes (RNG global
        # + état sim), donc identiques sur les deux machines
        self.ais = [AIController(self, p, diff, self.diff_key)
                for p in self.combatants if p.is_ai]
        start = self.start_pos[self.local_pid]
        self.cam = Vector2(clamp(start.x - VIEW_W / 2, 0, self.world_w - VIEW_W),
                           clamp(start.y - VIEW_H / 2, 0, self.world_h - VIEW_H))
        # brouillard de guerre (purement visuel : la simulation n'en dépend pas,
        # chaque machine calcule le sien à partir des unités de son équipe)
        self.fog_explored = bytearray(self.map_w * self.map_h)
        self.fog_visible = bytearray(self.map_w * self.map_h)
        self.fog_timer = 0.0
        self.fog_version = 0
        self._fog_cache = None
        self._fog_mini = None
        self.update_fog()
        if len(self.combatants) == 2:
            self.message("Détruisez tous les bâtiments de " + self.enemy_name + " !",
                         C_TEXT, 6)
        elif self.survival_mode:
            self.message("Mode Survie zombie : tenez le plus longtemps possible !",
                         C_TEXT, 6)
        else:
            self.message("Détruisez les bâtiments de toutes les équipes ennemies !",
                         C_TEXT, 6)
        self.message("F1 : aide et commandes", C_DIM, 6)
        self.survival_prep_duration = float(self.config["zombie_invasion_delay"])
        self.survival_prep_left = self.survival_prep_duration
        self.survival_started = (not self.survival_mode) or self.survival_prep_duration <= 0
        self.survival_time = 0.0
        self.survival_spawn_interval = float(self.config["zombie_spawn_interval"])
        self.survival_spawn_t = self.survival_spawn_interval
        self.survival_target = 0
        self.survival_scores = []
        self.survival_best = 0
        self.survival_new_record = False
        self.survival_saved = False
        if self.survival_mode:
            self.load_survival_scores()
            if self.survival_started:
                self.message("Les zombies arrivent !", C_BAD, 6)
            else:
                mins, secs = divmod(int(self.survival_prep_duration), 60)
                self.message(f"Préparation : {mins:02d}:{secs:02d} avant l'invasion zombie.",
                             C_DIM, 6)

    @property
    def me(self):
        return self.players[self.local_pid]

    @property
    def combatants(self):
        """Les joueurs réguliers (sans le joueur zombie)."""
        return [p for p in self.players if p.pid != ZOMBIE_PID]

    @property
    def zombie_player(self):
        return self.zombie_p

    @property
    def survival_score_path(self):
        return os.path.join(os.path.dirname(__file__), "survival_scores.json")

    def load_survival_scores(self):
        self.survival_scores = []
        try:
            with open(self.survival_score_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            times = [int(v) for v in data.get("times", []) if isinstance(v, (int, float))]
            self.survival_scores = sorted(times, reverse=True)[:20]
        except Exception:
            self.survival_scores = []
        self.survival_best = self.survival_scores[0] if self.survival_scores else 0

    def save_survival_score(self):
        score = int(self.survival_time)
        scores = list(self.survival_scores)
        scores.append(score)
        scores = sorted(scores, reverse=True)[:20]
        data = {"times": scores}
        try:
            with open(self.survival_score_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=True, indent=2)
        except Exception:
            return
        self.survival_scores = scores
        self.survival_new_record = score > self.survival_best
        self.survival_best = scores[0]

    def random_survival_point(self):
        return Vector2(random.uniform(48, self.world_w - 48),
                       random.uniform(48, self.world_h - 48))

    def spawn_border_zombie(self):
        if self.zombie_p is None:
            return None
        edge = random.randint(0, 3)
        margin = 16
        if edge == 0:
            pos = (margin, random.uniform(margin, self.world_h - margin))
        elif edge == 1:
            pos = (self.world_w - margin, random.uniform(margin, self.world_h - margin))
        elif edge == 2:
            pos = (random.uniform(margin, self.world_w - margin), margin)
        else:
            pos = (random.uniform(margin, self.world_w - margin), self.world_h - margin)
        z = self.spawn_unit("zombie", self.zombie_p, pos)
        z.order_move(self.random_survival_point(), amove=True)
        return z

    def update_survival_zombies(self, dt):
        """Invasion du mode Survie : maintient survival_target zombies vivants
        (un de plus à chaque intervalle, remplacement immédiat des morts) et
        les fait errer en hordes. Solo uniquement : le RNG global est consommé,
        ce qui serait interdit dans un code exécuté en LAN."""
        if not self.survival_mode or self.zombie_p is None \
                or not self.survival_started:
            return
        self.survival_spawn_t -= dt
        while self.survival_spawn_t <= 0:
            self.survival_spawn_t += self.survival_spawn_interval
            self.survival_target += 1
        zombies = sorted((u for u in self.units
                          if u.owner is self.zombie_p and u.kind == "zombie"),
                         key=lambda u: u.uid)
        for _ in range(self.survival_target - len(zombies)):
            z = self.spawn_border_zombie()
            if z is not None:
                zombies.append(z)  # uid croissant : l'ordre trié est conservé
        for i, z in enumerate(zombies):
            if z.state == "attack" and z.attack_target is not None and z.attack_target.hp > 0:
                continue
            leader = None
            for other in zombies[:i]:
                if z.pos.distance_to(other.pos) <= 46 and other.dest is not None:
                    leader = other
                    break
            if leader is not None and leader.dest is not None:
                if z.dest is None or z.dest.distance_to(leader.dest) > 14:
                    z.order_move(Vector2(leader.dest), amove=True)
                continue
            if z.state == "idle" or z.dest is None or z.pos.distance_to(z.dest) < 18:
                z.order_move(self.random_survival_point(), amove=True)

    # ------------------------------------------------------------ carte
    def gen_map(self):
        # les positions sont relatives à map_w/map_h (taille paramétrable) et
        # au nombre de joueurs : 2 = coins opposés, sinon bases en ellipse
        mw, mh = self.map_w, self.map_h
        self.bg = art.Terrain(self.world_w, self.world_h, TILE)
        combats = self.combatants
        n = len(combats)
        if self.survival_mode:
            # Décalage volontaire du QG en Survie pour éviter la superposition
            # avec le gisement central de cristaux.
            base_tiles = [(mw // 2 - 8, mh // 2 + 2)]
        elif n == 2:
            base_tiles = [(5, mh - 11), (mw - 9, 6)]
        else:
            cx0, cy0 = mw / 2, mh / 2
            rx, ry = mw / 2 - 9, mh / 2 - 7
            base_tiles = []
            for i in range(n):
                a = math.tau * (i / n + 0.375)  # joueur 0 en bas à gauche
                tx = int(round(cx0 + math.cos(a) * rx)) - 2
                ty = int(round(cy0 + math.sin(a) * ry)) - 1
                base_tiles.append((int(clamp(tx, 2, mw - 7)),
                                   int(clamp(ty, 2, mh - 6))))
        base_px = [(tx * TILE + 64, ty * TILE + 48) for tx, ty in base_tiles]
        center_px = (self.world_w / 2, self.world_h / 2)
        for i, (bx, by) in enumerate(base_px):
            art.bake_plaza(self.bg, bx, by, 118, seed=3 + i)
            if n > 2:
                art.bake_path(self.bg, (bx, by), center_px, seed=5 + i)
        if n == 2:
            art.bake_path(self.bg, base_px[0], base_px[1])

        def cluster(cx, cy, num, amount):
            for i in range(num):
                a = i / num * math.tau + random.uniform(-0.3, 0.3)
                d = random.uniform(30, 75)
                self.crystals.append(Crystal(cx * TILE + math.cos(a) * d,
                                             cy * TILE + math.sin(a) * d,
                                             amount + random.randint(-200, 200)))

        # un gisement proche de chaque base, décalé vers le centre de la carte
        for tx, ty in base_tiles:
            v = Vector2(mw / 2 - (tx + 2), mh / 2 - (ty + 1))
            if v.length_squared() > 0:
                v.scale_to_length(7.5)
            cluster(tx + 2 + v.x, ty + 1 + v.y, 5, 1600)
        cluster(mw * 0.50, mh * 0.50, 6, 2200)
        for fx, fy, num, amount in ((0.22, 0.20, 4, 1800), (0.78, 0.80, 4, 1800),
                                    (0.47, 0.86, 3, 1400), (0.53, 0.14, 3, 1400)):
            cluster(mw * fx, mh * fy, num, amount)

        # forêts et rochers (décor) — densité constante quelle que soit la carte
        area = mw * mh / (64 * 44)
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
            gx, gy = rng.randint(60, self.world_w - 60), rng.randint(60, self.world_h - 60)
            if not far_enough(gx, gy):
                continue
            for _ in range(rng.randint(3, 6)):
                x = gx + rng.randint(-70, 70)
                y = gy + rng.randint(-55, 55)
                if 30 < x < self.world_w - 30 and 30 < y < self.world_h - 30 \
                        and far_enough(x, y):
                    self.doodads.append(Doodad("tree", x, y, rng.randint(0, 99)))
        for _ in range(int(14 * area)):
            x, y = rng.randint(40, self.world_w - 40), rng.randint(40, self.world_h - 40)
            if far_enough(x, y, 200, 60):
                self.doodads.append(Doodad("rock", x, y, rng.randint(0, 99)))

        self.start_pos = []
        for p, (tx, ty) in zip(combats, base_tiles):
            b = Building("qg", p, tx, ty, done=True)
            self.buildings.append(b)
            self.start_pos.append(Vector2(b.rect.center))
            for _ in range(4):
                u = self.spawn_unit("ouvrier", p, b.spawn_point())
                c = self.nearest_crystal(u.pos)
                if c is not None:
                    u.order_harvest(c)

        # mode zombie classique : quelques rôdeurs dispersés, loin des bases de
        # départ (seuil dégressif : les grandes parties laissent moins de place).
        # En mode Survie, aucun zombie n'est présent au démarrage : la première
        # vague arrive via update_survival_zombies().
        if self.zombies_on and not self.survival_mode:
            num = int(clamp(mw * mh // 400, 4, 12))
            placed = 0
            for dmin in (600, 450, 300):
                tries = 0
                while placed < num and tries < 300:
                    tries += 1
                    x = random.uniform(80, self.world_w - 80)
                    y = random.uniform(80, self.world_h - 80)
                    if all(math.hypot(x - bx, y - by) > dmin for bx, by in base_px):
                        self.spawn_unit("zombie", self.zombie_p, (x, y))
                        placed += 1
                if placed >= num:
                    break

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

    def drop_caca(self, pos):
        """Petit caca d'Adryann : décor cosmétique, s'estompe comme un cadavre."""
        self.corpses.append([art.caca_sprite(), Vector2(pos), 10.0, 10.0])

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
        # Adryann dévore sa victime : +10% de ses PV max, et pas de cadavre
        eaten = (isinstance(attacker, Unit) and attacker.kind == "adryann"
                 and attacker.hp > 0)
        if eaten:
            attacker.hp = min(attacker.max_hp, attacker.hp + attacker.max_hp * 0.10)
            self.ring(unit.pos, 20, (238, 160, 140))
            self.spark(unit.pos, (238, 160, 140), 6)
            self.add_particle("glow", attacker.pos, (0, 0), 0.25,
                              color=(120, 200, 110), size=18)
        else:
            # cadavre qui s'estompe
            fr = art.unit_frames(unit.kind, unit.owner.pid)[art.frame_index(unit.facing)]
            c = fr.copy()
            c.fill((110, 110, 110, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.corpses.append([c, Vector2(unit.pos), 6.0, 6.0])
        self.spark(unit.pos, unit.owner.colors["light"], 8)
        self.add_particle("smoke", unit.pos, (0, -14), 1.2, size=5)
        self.play("die")
        # mode zombie : une pierre tombale, puis un zombie (les zombies
        # eux-mêmes ne se relèvent pas ; une victime dévorée ne laisse rien)
        if self.zombies_on and unit.kind != "zombie" and not eaten:
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
        elif not b.owner.allied(self.me):
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
        if not 0 <= pid < len(self.combatants):
            return
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
        if isinstance(ent, (Unit, Building)) and not ent.owner.allied(p):
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
                # l'ouvrier déjà en chantier met le nouveau bâtiment en file
                # et l'enchaînera automatiquement
                if u.state == "build" and u.build_target is not None \
                        and u.build_target.hp > 0:
                    u.build_queue.append(b)
                else:
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
        """Grille map_w×map_h des cases occupées par un bâtiment (1 = bloqué).
        Les portes de l'équipe de `owner` sont considérées passantes."""
        mw, mh = self.map_w, self.map_h
        key = (self.block_version, owner.team)
        if self._block_cache_key != key:
            grid = bytearray(mw * mh)
            for b in self.buildings:
                if b.kind == "porte" and b.owner.allied(owner):
                    continue
                tx0 = max(0, b.rect.left // TILE)
                ty0 = max(0, b.rect.top // TILE)
                tx1 = min(mw - 1, (b.rect.right - 1) // TILE)
                ty1 = min(mh - 1, (b.rect.bottom - 1) // TILE)
                for ty in range(ty0, ty1 + 1):
                    row = ty * mw
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
        mw, mh = self.map_w, self.map_h
        grid = self.tile_blocked_map(owner)
        sx = int(clamp(start.x // TILE, 0, mw - 1))
        sy = int(clamp(start.y // TILE, 0, mh - 1))
        gx = int(clamp(goal.x // TILE, 0, mw - 1))
        gy = int(clamp(goal.y // TILE, 0, mh - 1))
        if grid[sy * mw + sx]:
            # coincé contre/dans un bâtiment : repartir de la case libre voisine
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = sx + dx, sy + dy
                    if 0 <= nx < mw and 0 <= ny < mh and not grid[ny * mw + nx]:
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
                if not (0 <= nx < mw and 0 <= ny < mh):
                    continue
                if grid[ny * mw + nx]:
                    continue
                # pas de coupe de coin le long d'un bâtiment
                if dx and dy and (grid[y * mw + nx] or grid[ny * mw + x]):
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
        mw, mh = self.map_w, self.map_h
        tcx, tcy = px / TILE, py / TILE
        r = radius_tiles
        x0, x1 = max(0, int(tcx - r)), min(mw - 1, int(tcx + r))
        y0, y1 = max(0, int(tcy - r)), min(mh - 1, int(tcy + r))
        r2 = r * r
        for ty in range(y0, y1 + 1):
            dy = ty + 0.5 - tcy
            row = ty * mw
            for tx in range(x0, x1 + 1):
                dx = tx + 0.5 - tcx
                if dx * dx + dy * dy <= r2:
                    vis[row + tx] = 1

    def update_fog(self):
        if AUTOTEST:
            return
        vis = bytearray(self.map_w * self.map_h)
        me = self.me
        for u in self.units:
            if u.owner.allied(me):
                self._reveal(vis, u.pos.x, u.pos.y, 5.5)
        for b in self.buildings:
            if b.owner.allied(me):
                self._reveal(vis, b.rect.centerx, b.rect.centery,
                             8.0 if b.kind == "tour" else 6.5)
        self.fog_visible = vis
        # exploré |= visible, sans boucle Python (octets 0/1 : le OU bit à
        # bit sur les entiers équivaut au OU case par case)
        exp = self.fog_explored
        merged = int.from_bytes(exp, "little") | int.from_bytes(vis, "little")
        self.fog_explored = bytearray(merged.to_bytes(len(exp), "little"))
        self.fog_version += 1

    def fog_state(self, x, y):
        """0 = inexploré, 1 = exploré mais hors de vue, 2 = visible."""
        tx, ty = int(x // TILE), int(y // TILE)
        if not (0 <= tx < self.map_w and 0 <= ty < self.map_h):
            return 0
        i = ty * self.map_w + tx
        if self.fog_visible[i]:
            return 2
        return 1 if self.fog_explored[i] else 0

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
            if u.owner.allied(owner) or u.hp <= 0:
                continue
            d = pos.distance_to(u.pos)
            if d <= radius and d - 30 < bd:
                best, bd = u, d - 30
        if not units_only:
            for b in self.buildings:
                if b.owner.allied(owner):
                    continue
                d = dist_point_rect(pos, b.rect)
                if d <= radius and d < bd:
                    best, bd = b, d
        return best

    def enemies_near_point(self, pos, radius, owner):
        out = [u for u in self.units
               if not u.owner.allied(owner) and pos.distance_to(u.pos) <= radius]
        out += [b for b in self.buildings
                if not b.owner.allied(owner) and dist_point_rect(pos, b.rect) <= radius]
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
        if tx < 0 or ty < 0 or tx + tw > self.map_w or ty + th > self.map_h:
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
        if self.survival_mode:
            if not self.survival_started:
                self.survival_prep_left = max(0.0, self.survival_prep_left - dt)
                if self.survival_prep_left <= 0:
                    self.survival_started = True
                    self.survival_spawn_t = self.survival_spawn_interval
                    self.message("Les zombies arrivent !", C_BAD, 6)
            else:
                self.survival_time += dt
        self.update_survival_zombies(dt)
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
                self.spawn_unit("zombie", self.zombie_p, t[0])
                self.ring(t[0], 30, (130, 220, 110))
                self.spark(t[0], (140, 230, 120), 6)
        self.tombstones = [t for t in self.tombstones if t[1] > 0]

        self.update_effects(dt)
        self.check_victory()

    def update_effects(self, dt):
        """Particules, anneaux, cadavres, messages : purement cosmétique."""
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

    def check_victory(self):
        """Une équipe gagne quand elle est la seule à avoir encore un bâtiment
        (les zombies ne comptent pas)."""
        if self.survival_mode:
            # Survie = solo uniquement, donc lire self.me ici est sans danger
            # (interdit sinon : la sim ne doit pas dépendre de l'état local).
            alive = any(b.owner is self.me and b.kind == "qg" for b in self.buildings)
            if not alive and self.winner is None:
                self.winner = ZOMBIE_TEAM
                self.play("lose")
                if not self.survival_saved:
                    self.save_survival_score()
                    self.survival_saved = True
            return
        alive = set()
        for p in self.combatants:
            if any(b.owner is p for b in self.buildings):
                alive.add(p.team)
            elif p.pid not in self.eliminated:
                self.eliminated.add(p.pid)
                self.message(f"{FACTION_NAMES[p.pid]} est éliminé !", C_BAD, 5)
        if self.winner is None and len(alive) <= 1:
            self.winner = next(iter(alive), None)
            if self.winner is not None:
                self.play("win" if self.winner == self.me.team else "lose")

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
                if b.kind == "porte" and b.open and b.owner.allied(u.owner):
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
            u.pos.x = clamp(u.pos.x, 4, self.world_w - 4)
            u.pos.y = clamp(u.pos.y, 4, self.world_h - 4)

    # ------------------------------------------------------------ entrées
    def handle_event(self, e):
        if self.paused and self.winner is None:
            self.handle_pause_menu_event(e)
            return
        if e.type == pygame.KEYDOWN:
            self.on_key(e)
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.on_mouse_down(e)
        elif e.type == pygame.MOUSEBUTTONUP:
            self.on_mouse_up(e)
        elif e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos

    def handle_pause_menu_event(self, e):
        _panel, resume_r, quit_r = self.pause_menu_rects()
        if e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
            return
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_p, pygame.K_ESCAPE):
                self.issue(dict(op="pause"))
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if resume_r.collidepoint(e.pos):
                self.issue(dict(op="pause"))
            elif quit_r.collidepoint(e.pos):
                # sortie purement locale : on quitte la boucle de jeu, la sim
                # n'est pas mutée (en LAN le pair reçoit un "bye")
                self.request_return_menu = True

    def pause_menu_rects(self):
        """Panneau et boutons du menu pause (source unique, utilisée aussi
        par le rendu)."""
        panel = pygame.Rect(SCREEN_W // 2 - 230, SCREEN_H // 2 - 107, 460, 214)
        resume_r = pygame.Rect(panel.x + 64, panel.bottom - 66, 146, 44)
        quit_r = pygame.Rect(panel.right - 210, panel.bottom - 66, 146, 44)
        return panel, resume_r, quit_r

    def on_key(self, e):
        k = e.key
        if k == pygame.K_F1:
            self.show_help = not self.show_help
            return
        if k == pygame.K_p:
            self.issue(dict(op="pause"))
            return
        if k == pygame.K_ESCAPE:
            # fin de partie ou connexion perdue : retour direct au menu (la
            # pause lockstep n'avancerait plus si le pair est déconnecté)
            if self.winner is not None or (self.net is not None
                                           and not self.net.alive):
                self.request_return_menu = True
            elif self.placing:
                self.placing = None
            elif self.selection:
                self.selection = []
            else:
                # rien à annuler : Échap ouvre le menu pause (confirmation
                # de sortie via le bouton QUITTER)
                self.issue(dict(op="pause"))
            return
        if pygame.K_1 <= k <= pygame.K_5:
            n = k - pygame.K_0
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                # les groupes acceptent unités ET bâtiments
                self.groups[n] = [s for s in self.selection
                                  if isinstance(s, (Unit, Building))
                                  and s.owner is self.me]
                self.message(f"Groupe {n} enregistré ({len(self.groups[n])} éléments)",
                             C_DIM, 2)
            elif n in self.groups:
                self.groups[n] = [s for s in self.groups[n] if s.hp > 0
                                  and (s in self.units or s in self.buildings)]
                if self.groups[n]:
                    self.selection = list(self.groups[n])
                    # double-appui : centrer la caméra sur le groupe (local)
                    now = time.monotonic()
                    if self._group_tap[0] == n and now - self._group_tap[1] < 0.4:
                        self.center_camera_on(self.selection)
                    self._group_tap = (n, now)
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
                self.cam.x = clamp(wx - VIEW_W / 2, 0, self.world_w - VIEW_W)
                self.cam.y = clamp(wy - VIEW_H / 2, 0, self.world_h - VIEW_H)
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
        # vignettes de sélection : clic = isoler, Shift+clic = retirer
        for rect, ent in getattr(self, "_sel_rects", []):
            if rect.collidepoint(mx, my):
                if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                    if ent in self.selection and len(self.selection) > 1:
                        self.selection.remove(ent)
                else:
                    self.selection = [ent]
                self.play("click")
                return

    def center_camera_on(self, ents):
        if not ents:
            return
        c = Vector2(0, 0)
        for s in ents:
            c += Vector2(s.rect.center) if isinstance(s, Building) else s.pos
        c /= len(ents)
        self.cam.x = clamp(c.x - VIEW_W / 2, 0, self.world_w - VIEW_W)
        self.cam.y = clamp(c.y - VIEW_H / 2, 0, self.world_h - VIEW_H)

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
        self.cam.x = clamp(self.cam.x + dx * CAM_SPEED * dt, 0, self.world_w - VIEW_W)
        self.cam.y = clamp(self.cam.y + dy * CAM_SPEED * dt, 0, self.world_h - VIEW_H)
