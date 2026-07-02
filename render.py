# -*- coding: utf-8 -*-
"""
CRISTALIS — rendu en jeu (mixin de Game) : monde, HUD, minimap, brouillard,
écrans d'aide et de fin. Purement local : rien ici ne doit modifier l'état de
simulation ni consommer le RNG global (invariant lockstep).
"""

import math

import pygame
from pygame.math import Vector2

import art
from art import clamp, lightc, shade
from data import (BUILD_HOTKEYS, BUILD_MENU, BUILDING_TYPES, C_BAD, C_CRYSTAL,
                  C_DIM, C_GOLD, C_GOOD, C_TEXT, DIFFICULTES, HUD_H,
                  PROD_HOTKEYS, SCREEN_H, SCREEN_W, TILE, TOPBAR_H,
                  UNIT_TYPES, UPGRADE_TYPES, VIEW_H, VIEW_W, prod_stats)
from entities import Building, Unit


class RenderMixin:
    """Toutes les méthodes de dessin de Game."""

    # ------------------------------------------------------- géométrie vue
    def screen_to_world(self, sx, sy):
        return Vector2(sx + self.cam.x, sy + self.cam.y)

    def minimap_rect(self):
        return pygame.Rect(10, SCREEN_H - HUD_H + 12, 210, HUD_H - 24)

    def minimap_to_world(self, mx, my):
        r = self.minimap_rect()
        return ((mx - r.x) / r.w * self.world_w, (my - r.y) / r.h * self.world_h)

    # --------------------------------------------------------- primitives
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

    def visible_to_me(self, ent):
        """Visibilité locale d'une entité ennemie à travers le brouillard.
        Les bâtiments restent visibles une fois repérés, pas les unités."""
        if isinstance(ent, Building):
            if ent.owner.allied(self.me):
                return True
            return self.fog_state(ent.rect.centerx, ent.rect.centery) > 0
        if ent.owner.allied(self.me):
            return True
        return self.fog_state(ent.pos.x, ent.pos.y) == 2

    # ------------------------------------------------------------- monde
    def draw(self, screen):
        cam = self.cam
        view = screen.subsurface((0, 0, VIEW_W, VIEW_H))
        view.blit(self.bg, (0, 0), (cam.x, cam.y, VIEW_W, VIEW_H))

        # couche sol : décombres, cadavres, pierres tombales
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
        # ne sont pas dessinés)
        drawables = []
        drawables.extend(self.crystals)
        drawables.extend(self.doodads)
        drawables.extend(b for b in self.buildings if self.visible_to_me(b))
        drawables.extend(u for u in self.units if self.visible_to_me(u))
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
            if not pr.owner.allied(self.me) and self.fog_state(pr.pos.x, pr.pos.y) < 2:
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

    # ------------------------------------------------------------ brouillard
    def draw_fog(self, view):
        cam = self.cam
        mw, mh = self.map_w, self.map_h
        tx0, ty0 = int(cam.x // TILE), int(cam.y // TILE)
        tw, th = VIEW_W // TILE + 2, VIEW_H // TILE + 2
        key = (tx0, ty0, self.fog_version)
        if self._fog_cache is None or self._fog_cache[0] != key:
            small = pygame.Surface((tw, th), pygame.SRCALPHA)
            for yy in range(th):
                ty = min(ty0 + yy, mh - 1)
                row = ty * mw
                for xx in range(tw):
                    i = row + min(tx0 + xx, mw - 1)
                    if self.fog_visible[i]:
                        continue
                    a = 116 if self.fog_explored[i] else 234
                    small.set_at((xx, yy), (8, 10, 18, a))
            scaled = pygame.transform.smoothscale(small, (tw * TILE, th * TILE))
            self._fog_cache = (key, scaled)
        view.blit(self._fog_cache[1], (tx0 * TILE - cam.x, ty0 * TILE - cam.y))

    # ------------------------------------------------------------ topbar
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
        n = len(self.combatants)
        if n == 2:
            t = f"vs {self.enemy_name}"
        else:
            t = f"{n} factions · équipe {p0.team}"
        t += "  (LAN)" if self.multiplayer \
            else f"  ({DIFFICULTES[self.diff_key]['nom']})"
        if self.speed > 1:
            t += f"  ·  ralenti ×{self.speed}"
        w = self.font.render(t, True, C_DIM).get_width()
        self.text(screen, self.font, t, p0.colors["light"], SCREEN_W - w - 12, 4)

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
                if s.kind == "ouvrier" and s.build_queue:
                    self.text(screen, self.font_s,
                              f"Chantiers en file : {len(s.build_queue)}",
                              C_GOLD, tx, y0 + 84)
            self.draw_hp_bar(screen, pr.x, pr.bottom + 6, pr.w,
                             s.hp / s.max_hp)
        elif self.selection:
            # vignettes : une par unité/bâtiment sélectionné (clic = isoler,
            # Shift+clic = retirer de la sélection)
            self.text(screen, self.font_b, f"{len(self.selection)} sélectionnés",
                      C_TEXT, x0, y0 - 2)
            per_row, size, pad = 14, 34, 4
            max_show = 42
            gx, gy = x0, y0 + 24
            for i, s in enumerate(self.selection[:max_show]):
                r = pygame.Rect(gx + (i % per_row) * (size + pad),
                                gy + (i // per_row) * (size + pad + 4), size, size)
                pygame.draw.rect(screen, (16, 18, 26), r)
                pygame.draw.rect(screen, (96, 108, 132), r, 1)
                if isinstance(s, Building):
                    ic = art.icon_building(s.kind, s.owner.pid, size - 6)
                else:
                    ic = art.icon_unit(s.kind, s.owner.pid, size - 6)
                screen.blit(ic, ic.get_rect(center=(r.centerx, r.centery - 1)))
                self.draw_hp_bar(screen, r.x + 2, r.bottom - 5, r.w - 4, s.hp / s.max_hp)
                self._sel_rects.append((r, s))
            if len(self.selection) > max_show:
                self.text(screen, self.font_s, f"+{len(self.selection) - max_show}",
                          C_DIM, gx + per_row * (size + pad) + 4, gy + 8)
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
        sx, sy = r.w / self.world_w, r.h / self.world_h
        for c in self.crystals:
            pygame.draw.circle(screen, C_CRYSTAL,
                               (int(r.x + c.pos.x * sx), int(r.y + c.pos.y * sy)), 2)
        for b in self.buildings:
            if not self.visible_to_me(b):
                continue
            pygame.draw.rect(screen, b.owner.colors["main"],
                             (r.x + b.rect.x * sx, r.y + b.rect.y * sy,
                              max(3, b.rect.w * sx), max(3, b.rect.h * sy)))
        for u in self.units:
            if not self.visible_to_me(u):
                continue
            screen.set_at((int(r.x + u.pos.x * sx), int(r.y + u.pos.y * sy)),
                          u.owner.colors["light"])
        # voile de brouillard sur la minimap
        if self._fog_mini is None or self._fog_mini[0] != self.fog_version:
            small = pygame.Surface((self.map_w, self.map_h), pygame.SRCALPHA)
            for ty in range(self.map_h):
                row = ty * self.map_w
                for tx in range(self.map_w):
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

    # ------------------------------------------------------------ overlays
    def draw_help(self, screen):
        w, h = 640, 508
        r = pygame.Rect(SCREEN_W / 2 - w / 2, VIEW_H / 2 - h / 2, w, h)
        screen.blit(art.panel_img(w, h), r.topleft)
        lines = [
            ("COMMANDES", C_CRYSTAL),
            ("Clic gauche / glisser : sélectionner", C_TEXT),
            ("Clic droit : déplacer / attaquer / récolter / reprendre un chantier", C_TEXT),
            ("A puis clic : attaque-déplacement (l'armée engage tout sur le chemin)", C_TEXT),
            ("Ctrl+1..5 : groupe (unités et bâtiments)    1..5 : rappeler    2× : centrer",
             C_TEXT),
            ("Shift + placements : l'ouvrier enchaîne les chantiers à la suite", C_TEXT),
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
            ("Caserne → Soldat [S], Maelan [N], Adryann [Y]", C_TEXT),
            ("Archerie → Archer [A], Mage [M]", C_TEXT),
            ("Forge → Golem [G], Baliste [B] (dégâts x3 sur les bâtiments)", C_TEXT),
            ("Tour de cristal : défense automatique", C_TEXT),
            ("Sanctuaire : améliore l'Attaque [A] et la Défense [D] (3 niveaux)", C_TEXT),
            ("Muraille [M] / Porte [E] : la porte ne s'ouvre que pour votre équipe", C_TEXT),
            ("", C_TEXT),
            ("Détruisez les bâtiments de toutes les équipes ennemies !", C_GOLD),
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
        win = self.winner == self.me.team
        txt = "VICTOIRE !" if win else "DÉFAITE..."
        col = (130, 235, 150) if win else (245, 105, 92)
        t = self.font_h.render(txt, True, col)
        for off in (3, 2):
            g = pygame.transform.smoothscale(
                t, (t.get_width() + off * 14, t.get_height() + off * 8))
            screen.blit(g, g.get_rect(center=(SCREEN_W / 2, 225)),
                        special_flags=pygame.BLEND_ADD)
        screen.blit(t, t.get_rect(center=(SCREEN_W / 2, 225)))
        if len(self.combatants) == 2:
            sub = ("La base de " + self.enemy_name + " est en ruines."
                   if win else self.enemy_name + " a rasé votre base.")
        else:
            sub = ("Votre équipe règne sur le champ de cristaux."
                   if win else "Votre équipe a été balayée.")
        self.text(screen, self.font_b, sub, C_TEXT, SCREEN_W // 2, 268, center=True)
        p0 = self.me
        mins, secs = divmod(int(self.time), 60)
        stats = [
            f"Durée : {mins:02d}:{secs:02d}",
            f"Cristaux récoltés : {p0.total_gathered}",
            f"Unités éliminées : {p0.units_killed}   Unités perdues : {p0.units_lost}",
        ]
        y = 330
        for line in stats:
            self.text(screen, self.font, line, C_DIM, SCREEN_W // 2, y, center=True)
            y += 26
        hint = ("Échap : retour au menu" if self.multiplayer
                else "R : rejouer      Échap : quitter")
        self.text(screen, self.font_b, hint, C_TEXT, SCREEN_W // 2, y + 30, center=True)
