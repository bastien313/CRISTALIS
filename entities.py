# -*- coding: utf-8 -*-
"""
CRISTALIS — entités de la simulation : joueurs, décor, cristaux, bâtiments,
unités et projectiles. Aucune entité ne touche au réseau ni aux entrées :
tout passe par les méthodes de Game reçues en paramètre (`game`).
"""

import math
import random

import pygame
from pygame.math import Vector2

import art
from data import (BUILDING_TYPES, C_CRYSTAL, C_GOLD, TILE, UNIT_TYPES,
                  UPGRADE_TYPES, VIEW_H, VIEW_W, dist_point_rect, prod_stats)


class Player:
    def __init__(self, pid, is_ai, income_mult=1.0, team=None):
        self.pid = pid
        self.is_ai = is_ai
        self.crystals = 300
        self.income_mult = income_mult
        self.team = pid + 1 if team is None else team
        self.colors = art.PLAYER_COLORS[pid]
        self.total_gathered = 0
        self.units_lost = 0
        self.units_killed = 0
        self.atk_level = 0
        self.def_level = 0

    def allied(self, other):
        return other.team == self.team

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
            px = p.x + math.cos(a) * 14 * ratio
            py = p.y + 8 + math.sin(a) * 3
            if 0 <= px < VIEW_W - 1 and 0 <= py < VIEW_H - 1:
                view.set_at((int(px), int(py)), (150, 220, 240))
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
        # la porte s'ouvre uniquement à l'approche d'une unité de son équipe
        if self.kind == "porte":
            self.open = any(u.owner.allied(self.owner)
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
        self.build_queue = []  # chantiers à enchaîner après le chantier courant
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
        self.build_queue = []

    def order_attack(self, target, auto=False):
        self.state = "attack"
        self.attack_target = target
        self.auto_target = auto
        if auto and self.anchor is None:
            self.anchor = Vector2(self.pos)
        if not auto:
            self.amove_dest = None
            self.build_target = None
            self.build_queue = []

    def order_harvest(self, crystal):
        if self.kind != "ouvrier":
            return
        self.state = "harvest"
        self.crystal = crystal
        self.attack_target = None
        self.build_target = None
        self.build_queue = []

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
                # chantier suivant dans la file (ordres de construction multiples)
                while self.build_queue:
                    nb = self.build_queue.pop(0)
                    if nb.hp > 0 and not nb.done:
                        self.order_build(nb)
                        return
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
