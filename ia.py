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
    def __init__(self, game, player, diff, diff_key="normal"):
        self.game = game
        self.p = player
        self.diff = diff
        self.diff_key = diff_key
        self.think_t = random.uniform(0.2, 0.8)
        self.wave_size = diff["wave0"]
        self.attack_mode = False
        self.prod_cd = 0.0
        self.commit_supply = 0.0

    def my(self, seq):
        return [e for e in seq if e.owner is self.p]

    def enemy_buildings(self):
        return [b for b in self.game.buildings if not b.owner.allied(self.p)]

    def enemy_units(self):
        return [u for u in self.game.units if not u.owner.allied(self.p)]

    def is_easy(self):
        return self.diff_key == "facile"

    def is_hard(self):
        return self.diff_key == "difficile"

    def think_interval(self):
        if self.is_easy():
            return 0.85
        if self.is_hard():
            return 0.35
        return 0.5

    def update(self, dt):
        g = self.game
        self.prod_cd = max(0, self.prod_cd - dt)
        self.think_t -= dt
        if self.think_t > 0:
            return
        self.think_t = self.think_interval()

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
        if len(pending) >= (3 if self.is_hard() else 2):
            self.assign_builders(pending, workers)
            return

        want = None
        supply_left = p.supply_cap(g) - p.supply_used(g)
        t = g.time / self.diff["tempo"]

        if self.is_easy():
            # Facile : tech limité et montée en puissance lente.
            if count("caserne") < 1 and len(workers) >= 4:
                want = "caserne"
            elif supply_left <= 5 and p.supply_cap(g) < 58:
                want = "obelisque"
            elif count("archerie") < 1 and t > 220:
                want = "archerie"
            elif count("obelisque") < 4 and t > 320 and supply_left <= 6:
                want = "obelisque"
            elif count("caserne") < 2 and t > 470:
                want = "caserne"
        elif self.is_hard():
            # Difficile : expansion agressive, fortification et tech complète.
            qg_target = 3 if t > 650 else (2 if t > 280 else 1)
            if count("qg") < qg_target and p.crystals > 520:
                want = "qg"
            elif supply_left <= 6 and p.supply_cap(g) < 90:
                want = "obelisque"
            elif count("caserne") < 2:
                want = "caserne"
            elif count("archerie") < 2 and t > 120:
                want = "archerie"
            elif count("forge") < 1 and t > 150:
                want = "forge"
            elif count("sanctuaire") < 1 and t > 180:
                want = "sanctuaire"
            elif count("tour") < max(3, count("qg") * 3) and t > 200:
                want = "tour"
            elif count("muraille") < count("qg") * 8 and t > 210 and p.crystals > 80:
                want = "muraille"
        else:
            # Normal : tous les bâtiments avec économie/défense équilibrées.
            if count("caserne") < 1 and len(workers) >= 4:
                want = "caserne"
            elif supply_left <= 4 and p.supply_cap(g) < 90:
                want = "obelisque"
            elif count("archerie") < 1 and t > 140:
                want = "archerie"
            elif count("tour") < 2 and t > 180:
                want = "tour"
            elif count("caserne") < 2 and t > 240:
                want = "caserne"
            elif count("forge") < 1 and t > 290:
                want = "forge"
            elif count("sanctuaire") < 1 and t > 320:
                want = "sanctuaire"
            elif count("qg") < 2 and t > 380 and p.crystals > 520:
                want = "qg"
            elif count("archerie") < 2 and t > 430:
                want = "archerie"
            elif count("tour") < 4 and t > 440:
                want = "tour"

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
        engaged = set()
        for b in pending:
            need = 1
            if self.is_hard() and b.kind in ("qg", "tour", "muraille"):
                need = 2
            elif not self.is_easy() and b.kind in ("forge", "sanctuaire"):
                need = 2

            assigned = [w for w in workers if w.build_target is b]
            while len(assigned) < need:
                free = [w for w in workers
                        if w not in engaged and w not in assigned
                        and w.state in ("idle", "harvest", "return")]
                if not free:
                    break
                w = min(free, key=lambda u: u.pos.distance_to(Vector2(b.rect.center)))
                w.order_build(b)
                engaged.add(w)
                assigned.append(w)

    def find_spot(self, kind, near_blds):
        g = self.game
        if not near_blds:
            return None
        qgs = [b for b in near_blds if b.kind == "qg"]
        for _ in range(70 if self.is_hard() else 50):
            base = random.choice(near_blds)
            ang = random.uniform(0, math.tau)
            d = random.uniform(2.2, 8.5) * TILE
            if kind == "tour":
                if qgs:
                    base = random.choice(qgs)
                center = Vector2(g.world_w / 2, g.world_h / 2)
                v = center - Vector2(base.rect.center)
                ang = math.atan2(v.y, v.x) + random.uniform(-1.0, 1.0)
                d = random.uniform(3.5, 9) * TILE
            if kind == "muraille":
                if qgs:
                    base = random.choice(qgs)
                center = Vector2(base.rect.center)
                to_mid = Vector2(g.world_w / 2, g.world_h / 2) - center
                ang = math.atan2(to_mid.y, to_mid.x) + random.uniform(-1.3, 1.3)
                d = random.uniform(3.8, 7.2) * TILE
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
        if self.is_easy():
            prefs = {
                "caserne": ["soldat", "soldat", "soldat", "soldat"],
                "archerie": ["archer", "archer", "archer"],
            }
            qlimit = 1
        elif self.is_hard():
            prefs = {
                "caserne": ["soldat", "soldat", "maelan", "adryann"],
                "archerie": ["archer", "archer", "mage", "mage"],
                "forge": ["golem", "baliste", "golem"],
                "sanctuaire": ["up_atq", "up_def", "up_atq", "up_def"],
            }
            qlimit = 3
        else:
            prefs = {
                "caserne": ["soldat", "soldat", "soldat", "maelan", "adryann"],
                "archerie": ["archer", "archer", "archer", "mage"],
                "forge": ["golem", "golem", "baliste"],
                "sanctuaire": ["up_atq", "up_def"],
            }
            qlimit = 2

        for kind, choices in prefs.items():
            for b in by_kind.get(kind, []):
                if b.done and len(b.queue) < qlimit:
                    if b.queue_unit(random.choice(choices), g):
                        produced = True
        return produced

    def reserve_supply(self):
        if self.is_easy():
            return 3
        if self.is_hard():
            return 10
        return 6

    def retreat_ratio(self):
        if self.is_easy():
            return 0.3
        return 0.5

    def home_point(self, blds):
        qgs = [b for b in blds if b.kind == "qg" and b.done]
        if qgs:
            return Vector2(qgs[0].rect.center)
        if blds:
            return Vector2(blds[0].rect.center)
        g = self.game
        return Vector2(g.world_w / 2, g.world_h / 2)

    def split_army(self, army, home):
        if not army:
            return [], []
        reserve = self.reserve_supply()
        pref = {"mage": 0, "archer": 1, "soldat": 2, "maelan": 3,
                "adryann": 3, "golem": 4, "baliste": 5}
        if self.is_easy():
            pref = {"archer": 0, "soldat": 1, "maelan": 2,
                    "adryann": 2, "golem": 3, "baliste": 4, "mage": 5}
        ranked = sorted(army,
                        key=lambda u: (pref.get(u.kind, 9),
                                       u.pos.distance_to(home),
                                       u.uid))
        keep, keep_supply = [], 0
        for u in ranked:
            if keep_supply >= reserve:
                break
            keep.append(u)
            keep_supply += UNIT_TYPES[u.kind]["supply"]
        keep_ids = {u.uid for u in keep}
        push = [u for u in army if u.uid not in keep_ids]
        return keep, push

    def local_threat(self, blds):
        g = self.game
        for b in blds:
            e = g.find_enemy_near_point(Vector2(b.rect.center), 300, self.p, units_only=True)
            if e is not None:
                return e
        return None

    def hold_garrison(self, defenders, home):
        for u in defenders:
            if u.state in ("idle", "move") and u.pos.distance_to(home) > 140:
                jitter = Vector2(random.uniform(-70, 70), random.uniform(-70, 70))
                u.order_move(home + jitter)

    def pick_priority_target(self, u, enemy_blds):
        if self.is_easy():
            return None
        scan = 260 if not self.is_hard() else 360
        danger = {"mage": 9, "baliste": 8, "golem": 7, "adryann": 6,
                  "maelan": 6, "archer": 5, "soldat": 4, "ouvrier": 1}
        near = [e for e in self.enemy_units() if u.dist_to(e) <= scan]
        if near:
            return min(near,
                       key=lambda e: (-danger.get(e.kind, 2), u.dist_to(e), e.uid))
        if self.is_hard() and enemy_blds:
            bprio = {"tour": 0, "sanctuaire": 1, "forge": 2, "archerie": 3,
                     "caserne": 4, "obelisque": 5, "qg": 6, "muraille": 7, "porte": 8}
            return min(enemy_blds, key=lambda b: (bprio.get(b.kind, 9), u.dist_to(b), b.uid))
        return None

    def retreat(self, units, home):
        for u in units:
            u.order_move(home + Vector2(random.uniform(-70, 70),
                                        random.uniform(-70, 70)))

    def combat(self, army, blds):
        g = self.game
        army_supply = sum(UNIT_TYPES[u.kind]["supply"] for u in army)
        home = self.home_point(blds)
        defenders, attackers = self.split_army(army, home)
        atk_supply = sum(UNIT_TYPES[u.kind]["supply"] for u in attackers)
        self.hold_garrison(defenders, home)

        threat = self.local_threat(blds)
        if threat is not None:
            for u in (army if not self.is_hard() else defenders + attackers[:max(3, len(attackers) // 2)]):
                if u.attack_target is None or u.auto_target:
                    u.order_attack(threat)
            if not self.is_hard():
                self.attack_mode = False
            return

        enemy_blds = self.enemy_buildings()
        if not enemy_blds:
            return

        effective_wave = min(self.wave_size, self.diff["wave_max"])
        supply_full = self.p.supply_used(g) >= self.p.supply_cap(g) - 2
        if not self.attack_mode and (atk_supply >= effective_wave
                                     or (supply_full and atk_supply >= 12)):
            self.attack_mode = True
            self.commit_supply = max(atk_supply, 1)
            g.message(f"{FACTION_NAMES[self.p.pid]} lance une offensive !", C_BAD)
            if not self.p.allied(g.me):
                g.play("alert")
        if self.attack_mode:
            if atk_supply <= max(2, self.commit_supply * self.retreat_ratio()):
                self.attack_mode = False
                self.wave_size = min(self.wave_size + self.diff["wave_step"],
                                     self.diff["wave_max"])
                self.retreat(attackers, home)
                return

            for u in attackers:
                if u.state == "idle" or (u.state == "move" and not u.amove):
                    tgt = self.pick_priority_target(u, enemy_blds)
                    if tgt is None:
                        tgt = min(enemy_blds, key=lambda b: u.dist_to(b))
                    if isinstance(tgt, Building):
                        u.order_move(Vector2(tgt.rect.center), amove=True)
                    else:
                        u.order_attack(tgt, auto=True)
        elif not self.is_easy() and army_supply >= 8:
            # Hors vague: petite pression tactique de reconnaissance.
            for u in attackers[:max(2, len(attackers) // 4)]:
                if u.state == "idle":
                    tgt = min(enemy_blds, key=lambda b: u.dist_to(b))
                    u.order_move(Vector2(tgt.rect.center), amove=True)
