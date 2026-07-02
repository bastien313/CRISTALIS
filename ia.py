# -*- coding: utf-8 -*-
"""
CRISTALIS — contrôleur d'IA d'un joueur.
Tourne dans la simulation (déterministe : RNG global + état sim uniquement),
donc identique des deux côtés en LAN même avec des IA dans la partie.
"""

import math
import random

from pygame.math import Vector2

from data import BUILDING_TYPES, C_BAD, FACTION_NAMES, TILE, UNIT_TYPES
from entities import Building


class AIController:
    def __init__(self, game, player, diff):
        self.game = game
        self.p = player
        self.diff = diff
        self.think_t = random.uniform(0.2, 0.8)
        self.wave_size = diff["wave0"]
        self.attack_mode = False
        self.prod_cd = 0.0

    def my(self, seq):
        return [e for e in seq if e.owner is self.p]

    def enemy_buildings(self):
        return [b for b in self.game.buildings if not b.owner.allied(self.p)]

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
                center = Vector2(g.world_w / 2, g.world_h / 2)
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

        enemy_blds = self.enemy_buildings()
        if not enemy_blds:
            return

        effective_wave = min(self.wave_size, self.diff["wave_max"])
        supply_full = self.p.supply_used(g) >= self.p.supply_cap(g) - 2
        if not self.attack_mode and (army_supply >= effective_wave
                                     or (supply_full and army_supply >= 12)):
            self.attack_mode = True
            g.message(f"{FACTION_NAMES[self.p.pid]} lance une offensive !", C_BAD)
            if not self.p.allied(g.me):
                g.play("alert")
        if self.attack_mode:
            if army_supply <= max(2, effective_wave * 0.25):
                self.attack_mode = False
                self.wave_size = min(self.wave_size + self.diff["wave_step"],
                                     self.diff["wave_max"])
                home = blds[0].rect.center if blds else (g.world_w / 2, g.world_h / 2)
                for u in army:
                    u.order_move(Vector2(home) + Vector2(random.uniform(-60, 60),
                                                         random.uniform(-60, 60)))
                return
            for u in army:
                if u.state == "idle" or (u.state == "move" and not u.amove):
                    tgt = min(enemy_blds, key=lambda b: u.dist_to(b))
                    u.order_move(Vector2(tgt.rect.center), amove=True)
