# -*- coding: utf-8 -*-
"""
CRISTALIS — couche graphique « pré-rendu » (style RTS des années 2000).
Tous les sprites sont peints procéduralement en super-échantillonnage
puis lissés (smoothscale), avec ombrage, contours et lumières.
"""

import math
import random

import pygame

WHITE = (255, 255, 255)

# Une entrée par faction (pid 0..7) + la dernière pour les zombies (pid 8).
PLAYER_COLORS = [
    dict(main=(64, 132, 245), dark=(30, 64, 128), light=(150, 198, 255)),   # Azur
    dict(main=(228, 74, 62), dark=(118, 34, 30), light=(255, 158, 145)),    # Karmin
    dict(main=(52, 190, 120), dark=(22, 88, 56), light=(150, 235, 185)),    # Émeraude
    dict(main=(156, 96, 235), dark=(74, 42, 120), light=(205, 170, 255)),   # Améthyste
    dict(main=(240, 150, 50), dark=(130, 76, 22), light=(255, 205, 140)),   # Ambre
    dict(main=(235, 110, 170), dark=(120, 48, 86), light=(255, 180, 215)),  # Églantine
    dict(main=(58, 200, 205), dark=(24, 96, 100), light=(150, 240, 240)),   # Turquoise
    dict(main=(222, 188, 64), dark=(112, 92, 26), light=(250, 228, 150)),   # Dorée
    dict(main=(108, 158, 76), dark=(48, 76, 40), light=(170, 224, 136)),    # Zombies
]

ART = {}          # cache global de surfaces
BUILD_EXT = 22    # dépassement vertical des sprites de bâtiments (toits)


# ------------------------------------------------------------------ couleurs
def clamp(v, a, b):
    return max(a, min(b, v))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def shade(c, f):
    return (clamp(int(c[0] * f), 0, 255),
            clamp(int(c[1] * f), 0, 255),
            clamp(int(c[2] * f), 0, 255))


def lightc(c, t):
    return mix(c, WHITE, t)


# ------------------------------------------------------------------- basiques
def vgrad(surf, rect, top, bot):
    x, y, w, h = rect
    for i in range(h):
        pygame.draw.line(surf, mix(top, bot, i / max(1, h - 1)),
                         (x, y + i), (x + w - 1, y + i))


def speckle(surf, rect, rng, n, amp=14):
    x, y, w, h = rect
    for _ in range(n):
        px, py = rng.randint(x, x + w - 1), rng.randint(y, y + h - 1)
        c = surf.get_at((px, py))
        d = rng.randint(-amp, amp)
        surf.set_at((px, py), (clamp(c[0] + d, 0, 255), clamp(c[1] + d, 0, 255),
                               clamp(c[2] + d, 0, 255)))


def bricks(surf, rect, col, step=10):
    x, y, w, h = rect
    for j in range(y + step, y + h, step):
        pygame.draw.line(surf, col, (x, j), (x + w - 1, j))
    off = 0
    for j in range(y, y + h - step, step):
        for i in range(x + (step if off else step // 2), x + w, step * 2):
            pygame.draw.line(surf, col, (i, j), (i, j + step))
        off = 1 - off


def draw_shard(surf, cx, cy, w, h, col):
    """Cristal facetté deux tons + contour + reflet."""
    pts = [(cx, cy - h), (cx + w * 0.62, cy - h * 0.2), (cx + w * 0.34, cy + h * 0.5),
           (cx - w * 0.34, cy + h * 0.5), (cx - w * 0.62, cy - h * 0.2)]
    pygame.draw.polygon(surf, col, pts)
    left = [(cx, cy - h), (cx - w * 0.62, cy - h * 0.2), (cx - w * 0.34, cy + h * 0.5),
            (cx, cy + h * 0.15)]
    pygame.draw.polygon(surf, lightc(col, 0.45), left)
    right = [(cx + w * 0.62, cy - h * 0.2), (cx + w * 0.34, cy + h * 0.5), (cx, cy + h * 0.15)]
    pygame.draw.polygon(surf, shade(col, 0.62), right)
    pygame.draw.polygon(surf, shade(col, 0.35), pts, max(1, int(w * 0.10)))
    pygame.draw.line(surf, lightc(col, 0.85), (cx - w * 0.16, cy - h * 0.72),
                     (cx - w * 0.30, cy - h * 0.28), max(1, int(w * 0.08)))


# ------------------------------------------------------------------- textures
def glow(color, r):
    key = ("glow", color, r)
    if key not in ART:
        s = pygame.Surface((r * 2, r * 2))
        for i in range(r, 0, -1):
            f = (1 - i / r) ** 2
            pygame.draw.circle(s, shade(color, f), (r, r), i)
        ART[key] = s
    return ART[key]


def smoke_tex(r):
    key = ("smoke", r)
    if key not in ART:
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i in range(r, 0, -1):
            a = int(70 * (1 - i / r) ** 1.4)
            pygame.draw.circle(s, (150, 150, 155, a), (r, r), i)
        ART[key] = s
    return ART[key]


def shadow_tex(w, h):
    key = ("shadow", w, h)
    if key not in ART:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(3):
            f = 1 - i * 0.28
            pygame.draw.ellipse(s, (0, 0, 0, 26 + i * 22),
                                (w * (1 - f) / 2, h * (1 - f) / 2, w * f, h * f))
        ART[key] = s
    return ART[key]


def sel_ring(r):
    key = ("ring", r)
    if key not in ART:
        w, h = r * 2 + 14, r + 10
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (60, 220, 90, 60), (0, 0, w, h), 5)
        pygame.draw.ellipse(s, (120, 255, 150, 160), (2, 2, w - 4, h - 4), 2)
        ART[key] = s
    return ART[key]


def vignette(w, h):
    key = ("vig", w, h)
    if key not in ART:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        n = 70
        for i in range(n):
            a = int(52 * (1 - i / n) ** 2)
            pygame.draw.rect(s, (8, 6, 16, a), (i, i, w - 2 * i, h - 2 * i), 1)
        ART[key] = s
    return ART[key]


# ---------------------------------------------------------------- unités
UNIT_CANVAS = {"ouvrier": 40, "soldat": 46, "archer": 44, "mage": 46, "golem": 62,
               "baliste": 56, "zombie": 44, "maelan": 44, "adryann": 52}
_METAL = (152, 160, 172)
_METAL_L = (204, 212, 222)
_SKIN = (232, 196, 158)
_WOOD = (110, 78, 46)


def _unit_canvas(kind, s):
    n = UNIT_CANVAS[kind] * s
    return pygame.Surface((n, n), pygame.SRCALPHA)


def _paint_ouvrier(d, s, col):
    c = UNIT_CANVAS["ouvrier"] * s // 2
    # pioche vers l'avant
    pygame.draw.line(d, _WOOD, (c + 2 * s, c + 1 * s), (c + 13 * s, c - 2 * s), 2 * s)
    pygame.draw.polygon(d, _METAL_L, [(c + 11 * s, c - 7 * s), (c + 16 * s, c - 2 * s),
                                      (c + 12 * s, c + 1 * s), (c + 11 * s, c - 3 * s)])
    pygame.draw.polygon(d, shade(_METAL, 0.6), [(c + 11 * s, c - 7 * s), (c + 16 * s, c - 2 * s),
                                                (c + 12 * s, c + 1 * s), (c + 11 * s, c - 3 * s)], s)
    # sac au dos
    pygame.draw.circle(d, (104, 78, 50), (c - 8 * s, c), 4 * s)
    pygame.draw.circle(d, (70, 52, 34), (c - 8 * s, c), 4 * s, s)
    # corps (tunique couleur d'équipe)
    pygame.draw.circle(d, shade(col["main"], 0.45), (c, c), 8 * s)
    pygame.draw.circle(d, col["main"], (c - s, c - s), 7 * s)
    pygame.draw.circle(d, lightc(col["main"], 0.4), (c - 3 * s, c - 3 * s), 3 * s)
    # épaules
    for dy in (-6, 6):
        pygame.draw.circle(d, shade(col["main"], 0.7), (c - s, c + dy * s), 3 * s)
        pygame.draw.circle(d, shade(col["main"], 0.4), (c - s, c + dy * s), 3 * s, s)
    # tête + capuche
    pygame.draw.circle(d, shade(col["dark"], 0.9), (c + 2 * s, c), 5 * s)
    pygame.draw.circle(d, _SKIN, (c + 3 * s, c), 3.6 * s)
    pygame.draw.circle(d, lightc(_SKIN, 0.5), (c + 2 * s, c - s), 1.6 * s)


def _paint_soldat(d, s, col):
    c = UNIT_CANVAS["soldat"] * s // 2
    # épée
    pygame.draw.polygon(d, _METAL_L, [(c + 7 * s, c - 2 * s), (c + 20 * s, c - 0.5 * s),
                                      (c + 20 * s, c + 0.5 * s), (c + 7 * s, c + 2 * s)])
    pygame.draw.line(d, WHITE, (c + 8 * s, c - s), (c + 19 * s, c), s)
    pygame.draw.line(d, (206, 172, 84), (c + 7 * s, c - 3 * s), (c + 7 * s, c + 3 * s), 2 * s)
    # bouclier (flanc)
    sh = pygame.Rect(0, 0, 9 * s, 13 * s)
    sh.center = (c - s, c - 9 * s)
    pygame.draw.ellipse(d, col["dark"], sh)
    pygame.draw.ellipse(d, lightc(col["main"], 0.25), sh.inflate(-3 * s, -3 * s))
    pygame.draw.ellipse(d, shade(col["dark"], 0.6), sh, s)
    pygame.draw.circle(d, (120, 226, 255), sh.center, 1.6 * s)
    # armure
    pygame.draw.circle(d, shade(_METAL, 0.5), (c, c), 9 * s)
    pygame.draw.circle(d, _METAL, (c - s, c - s), 8 * s)
    pygame.draw.polygon(d, col["main"], [(c - 3 * s, c - 7 * s), (c + 3 * s, c - 7 * s),
                                         (c + 2 * s, c + 7 * s), (c - 2 * s, c + 7 * s)])
    pygame.draw.circle(d, _METAL_L, (c - 3 * s, c - 3 * s), 3 * s)
    # épaulières
    for dy in (-7, 7):
        pygame.draw.circle(d, _METAL, (c - s, c + dy * s), 3.6 * s)
        pygame.draw.circle(d, shade(_METAL, 0.5), (c - s, c + dy * s), 3.6 * s, s)
    # casque + plumet
    pygame.draw.line(d, col["main"], (c - 3 * s, c), (c - 10 * s, c), 3 * s)
    pygame.draw.circle(d, _METAL_L, (c + s, c), 5 * s)
    pygame.draw.circle(d, shade(_METAL, 0.45), (c + s, c), 5 * s, s)
    pygame.draw.line(d, (40, 40, 46), (c + 4 * s, c - s), (c + 6 * s, c), s)
    pygame.draw.line(d, (40, 40, 46), (c + 4 * s, c + s), (c + 6 * s, c), s)


def _paint_archer(d, s, col):
    c = UNIT_CANVAS["archer"] * s // 2
    # cape flottant derrière
    pygame.draw.polygon(d, shade(col["main"], 0.45),
                        [(c - 2 * s, c - 8 * s), (c - 14 * s, c - 2 * s),
                         (c - 15 * s, c + 3 * s), (c - 2 * s, c + 8 * s)])
    pygame.draw.polygon(d, shade(col["main"], 0.3),
                        [(c - 2 * s, c - 8 * s), (c - 14 * s, c - 2 * s),
                         (c - 15 * s, c + 3 * s), (c - 2 * s, c + 8 * s)], s)
    # carquois
    pygame.draw.line(d, (96, 66, 40), (c - 8 * s, c + 6 * s), (c - 12 * s, c + 9 * s), 3 * s)
    # corps
    pygame.draw.circle(d, shade(col["main"], 0.5), (c, c), 7 * s)
    pygame.draw.circle(d, col["main"], (c - s, c - s), 6 * s)
    pygame.draw.circle(d, lightc(col["main"], 0.35), (c - 3 * s, c - 3 * s), 2.4 * s)
    # capuche sombre
    pygame.draw.circle(d, shade(col["dark"], 1.0), (c + s, c), 5 * s)
    pygame.draw.circle(d, shade(col["dark"], 0.55), (c + s, c), 5 * s, s)
    pygame.draw.circle(d, (26, 22, 20), (c + 3 * s, c), 2.6 * s)
    # arc + corde + flèche
    rect = pygame.Rect(c - 4 * s, c - 10 * s, 20 * s, 20 * s)
    pygame.draw.arc(d, (120, 84, 48), rect, -1.15, 1.15, 2 * s)
    tip1 = (c + 6 * s + 9.2 * s * 0.41, c - 9.2 * s * 0.91)
    tip2 = (c + 6 * s + 9.2 * s * 0.41, c + 9.2 * s * 0.91)
    pygame.draw.line(d, (222, 222, 226), tip1, tip2, s)
    pygame.draw.line(d, (140, 104, 62), (c - 2 * s, c), (c + 13 * s, c), int(1.4 * s))
    pygame.draw.polygon(d, _METAL_L, [(c + 15 * s, c), (c + 12 * s, c - 1.6 * s),
                                      (c + 12 * s, c + 1.6 * s)])
    pygame.draw.line(d, col["light"], (c - 2 * s, c), (c + 1 * s, c), 2 * s)


def _paint_mage(d, s, col):
    c = UNIT_CANVAS["mage"] * s // 2
    robe = mix(col["main"], (128, 70, 210), 0.5)
    # robe évasée
    pygame.draw.circle(d, shade(robe, 0.45), (c, c), 8.5 * s)
    pygame.draw.circle(d, robe, (c - s, c - s), 7.5 * s)
    pygame.draw.circle(d, lightc(robe, 0.35), (c - 3 * s, c - 3 * s), 3 * s)
    # liseré doré
    pygame.draw.circle(d, (212, 182, 96), (c, c), 8.5 * s, s)
    # étoiles brodées
    for a in (0.7, 2.6, 4.4):
        px, py = c + math.cos(a) * 5 * s, c + math.sin(a) * 5 * s
        pygame.draw.circle(d, lightc(robe, 0.7), (px, py), 0.9 * s)
    # capuche
    pygame.draw.circle(d, shade(robe, 0.7), (c + s, c), 5 * s)
    pygame.draw.circle(d, shade(robe, 0.4), (c + s, c), 5 * s, s)
    pygame.draw.circle(d, (24, 18, 30), (c + 3 * s, c), 2.8 * s)
    for dy in (-1.2, 1.2):
        pygame.draw.circle(d, (140, 240, 255), (c + 3.4 * s, c + dy * s), 0.8 * s)
    # bâton + cristal
    pygame.draw.line(d, _WOOD, (c - 7 * s, c + 8 * s), (c + 11 * s, c - 7 * s), 2 * s)
    draw_shard(d, c + 12 * s, c - 8 * s, 3.4 * s, 4.6 * s, (110, 225, 255))


def _paint_golem(d, s, col):
    c = UNIT_CANVAS["golem"] * s // 2
    rock = (122, 120, 116)
    rng = random.Random(4)
    # corps rocheux irrégulier
    pts = []
    for i in range(10):
        a = i / 10 * math.tau
        r = (12 + rng.uniform(-1.6, 2.4)) * s
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    pygame.draw.polygon(d, shade(rock, 0.55), pts)
    pts2 = [(x - 1.2 * s, y - 1.2 * s) for x, y in pts]
    pygame.draw.polygon(d, rock, pts2)
    pygame.draw.polygon(d, shade(rock, 0.4), pts, s)
    # plaques claires
    pygame.draw.polygon(d, lightc(rock, 0.22),
                        [(c - 8 * s, c - 8 * s), (c - s, c - 11 * s), (c + 3 * s, c - 5 * s),
                         (c - 5 * s, c - 2 * s)])
    # fissures
    for a0 in (0.6, 2.4, 4.0):
        x0, y0 = c + math.cos(a0) * 4 * s, c + math.sin(a0) * 4 * s
        x1, y1 = c + math.cos(a0 + 0.4) * 10 * s, c + math.sin(a0 + 0.4) * 10 * s
        pygame.draw.line(d, shade(rock, 0.42), (x0, y0), (x1, y1), s)
    # mousse
    for a0 in (1.8, 3.4, 5.2):
        pygame.draw.circle(d, (74, 104, 56),
                           (c + math.cos(a0) * 8 * s, c + math.sin(a0) * 8 * s), 1.6 * s)
    # poings
    for dy in (-9, 9):
        pygame.draw.circle(d, shade(rock, 0.8), (c + 9 * s, c + dy * s), 5 * s)
        pygame.draw.circle(d, shade(rock, 0.45), (c + 9 * s, c + dy * s), 5 * s, s)
    # tête
    pygame.draw.circle(d, rock, (c + 9 * s, c), 4.4 * s)
    pygame.draw.circle(d, shade(rock, 0.45), (c + 9 * s, c), 4.4 * s, s)
    for dy in (-1.4, 1.4):
        pygame.draw.circle(d, col["light"], (c + 11 * s, c + dy * s), 1.0 * s)
    # cœur de cristal (creux, la lueur est dynamique)
    pygame.draw.circle(d, (30, 28, 34), (c, c), 3.6 * s)
    pygame.draw.circle(d, mix(col["main"], (140, 240, 255), 0.4), (c, c), 2.4 * s)


def _paint_baliste(d, s, col):
    c = UNIT_CANVAS["baliste"] * s // 2
    # roues
    for dy in (-8, 8):
        pygame.draw.circle(d, (52, 40, 26), (c - 4 * s, c + dy * s), 4.6 * s)
        pygame.draw.circle(d, (86, 62, 38), (c - 4 * s, c + dy * s), 4.6 * s, s)
        pygame.draw.circle(d, (30, 24, 16), (c - 4 * s, c + dy * s), 1.4 * s)
    # châssis en bois
    frame = [(c - 12 * s, c - 3 * s), (c + 6 * s, c - 5 * s),
             (c + 6 * s, c + 5 * s), (c - 12 * s, c + 3 * s)]
    pygame.draw.polygon(d, _WOOD, frame)
    pygame.draw.polygon(d, shade(_WOOD, 0.55), frame, s)
    pygame.draw.line(d, lightc(_WOOD, 0.25), (c - 10 * s, c - s), (c + 4 * s, c - 2 * s), s)
    # treuil arrière
    pygame.draw.circle(d, shade(_WOOD, 0.7), (c - 9 * s, c), 2.6 * s)
    pygame.draw.circle(d, (40, 32, 20), (c - 9 * s, c), 2.6 * s, s)
    # bras d'arc + corde
    pygame.draw.line(d, (120, 84, 48), (c + 6 * s, c - s), (c + 1 * s, c - 12 * s), 2 * s)
    pygame.draw.line(d, (120, 84, 48), (c + 6 * s, c + s), (c + 1 * s, c + 12 * s), 2 * s)
    pygame.draw.line(d, (222, 222, 226), (c + 1 * s, c - 12 * s), (c + 1 * s, c + 12 * s), s)
    # gros carreau métallique
    pygame.draw.line(d, (140, 104, 62), (c - 7 * s, c), (c + 13 * s, c), 2 * s)
    pygame.draw.polygon(d, _METAL_L, [(c + 17 * s, c), (c + 12 * s, c - 2.2 * s),
                                      (c + 12 * s, c + 2.2 * s)])
    # fanion couleur d'équipe
    pygame.draw.line(d, (120, 118, 124), (c - 12 * s, c - 3 * s), (c - 12 * s, c - 10 * s), s)
    pygame.draw.polygon(d, col["main"], [(c - 12 * s, c - 10 * s), (c - 7 * s, c - 8.5 * s),
                                         (c - 12 * s, c - 7 * s)])


def _paint_zombie(d, s, col):
    c = UNIT_CANVAS["zombie"] * s // 2
    skin = (134, 172, 96)
    rags = (74, 82, 60)
    # bras décharnés tendus vers l'avant
    for dy in (-4, 4):
        pygame.draw.line(d, skin, (c, c + dy * s), (c + 11 * s, c + dy * 0.6 * s), 3 * s)
        pygame.draw.circle(d, lightc(skin, 0.2), (c + 11 * s, c + dy * 0.6 * s), 1.8 * s)
    # corps voûté en haillons
    pygame.draw.circle(d, shade(rags, 0.6), (c - s, c), 8 * s)
    pygame.draw.circle(d, rags, (c - 2 * s, c - s), 7 * s)
    pygame.draw.circle(d, shade(col["dark"], 0.9), (c - 2 * s, c - s), 7 * s, s)
    # déchirures
    pygame.draw.line(d, shade(rags, 0.4), (c - 6 * s, c - 3 * s), (c - 1 * s, c + 2 * s), s)
    pygame.draw.line(d, shade(rags, 0.4), (c - 5 * s, c + 4 * s), (c - 1 * s, c - 1 * s), s)
    # tête verdâtre penchée en avant
    pygame.draw.circle(d, shade(skin, 0.55), (c + 3 * s, c), 5 * s)
    pygame.draw.circle(d, skin, (c + 3 * s, c - 0.5 * s), 4.4 * s)
    # yeux rouges
    for dy in (-1.6, 1.6):
        pygame.draw.circle(d, (215, 62, 50), (c + 5.5 * s, c + dy * s), 1.0 * s)
    # mâchoire sombre entrouverte
    pygame.draw.line(d, (40, 44, 34), (c + 6 * s, c + 2 * s), (c + 7.5 * s, c + 2.6 * s), s)


def _paint_maelan(d, s, col):
    c = UNIT_CANVAS["maelan"] * s // 2
    ink = (34, 36, 46)      # tenue de ninja sombre
    ink_l = (58, 62, 78)
    # katana tendu vers l'avant
    pygame.draw.polygon(d, _METAL_L, [(c + 6 * s, c - 1.4 * s), (c + 19 * s, c - 0.4 * s),
                                      (c + 19 * s, c + 0.4 * s), (c + 6 * s, c + 1.4 * s)])
    pygame.draw.line(d, WHITE, (c + 7 * s, c - 0.6 * s), (c + 18 * s, c), s)
    pygame.draw.line(d, (60, 52, 40), (c + 6 * s, c - 2.4 * s), (c + 6 * s, c + 2.4 * s), 2 * s)
    # écharpe couleur d'équipe flottant derrière
    pygame.draw.polygon(d, col["main"],
                        [(c - 2 * s, c - 4 * s), (c - 13 * s, c - 7 * s),
                         (c - 15 * s, c - 2 * s), (c - 4 * s, c)])
    pygame.draw.polygon(d, shade(col["main"], 0.55),
                        [(c - 2 * s, c - 4 * s), (c - 13 * s, c - 7 * s),
                         (c - 15 * s, c - 2 * s), (c - 4 * s, c)], s)
    # corps compact accroupi
    pygame.draw.circle(d, shade(ink, 0.7), (c, c), 7 * s)
    pygame.draw.circle(d, ink_l, (c - s, c - s), 6 * s)
    pygame.draw.circle(d, lightc(ink_l, 0.2), (c - 3 * s, c - 3 * s), 2.2 * s)
    # ceinture couleur d'équipe
    pygame.draw.line(d, col["main"], (c - 6 * s, c + 2 * s), (c + 5 * s, c + 2 * s), 2 * s)
    # seconde lame dans le dos
    pygame.draw.line(d, shade(_METAL, 0.8), (c - 6 * s, c + 6 * s), (c - 11 * s, c + 10 * s), 2 * s)
    # tête masquée + bandeau d'équipe
    pygame.draw.circle(d, ink, (c + 2 * s, c), 4.6 * s)
    pygame.draw.circle(d, shade(ink, 0.5), (c + 2 * s, c), 4.6 * s, s)
    pygame.draw.line(d, col["main"], (c - s, c - 3.4 * s), (c + 3 * s, c - 3.8 * s), int(1.6 * s))
    # fente du masque : yeux clairs
    pygame.draw.line(d, _SKIN, (c + 3.4 * s, c - 1.6 * s), (c + 5.6 * s, c - 0.4 * s), int(1.8 * s))
    for dy in (-1.5, 0.4):
        pygame.draw.circle(d, (32, 30, 36), (c + 4.8 * s, c + dy * s), 0.7 * s)


def _paint_adryann(d, s, col):
    c = UNIT_CANVAS["adryann"] * s // 2
    skin = _SKIN
    # gros bidon rond en tunique couleur d'équipe
    pygame.draw.circle(d, shade(col["main"], 0.45), (c, c), 11 * s)
    pygame.draw.circle(d, col["main"], (c - s, c - s), 10 * s)
    pygame.draw.circle(d, lightc(col["main"], 0.35), (c - 4 * s, c - 4 * s), 4 * s)
    # ventre qui déborde de la tunique
    pygame.draw.circle(d, shade(skin, 0.85), (c + 3 * s, c), 5.5 * s)
    pygame.draw.circle(d, skin, (c + 2.5 * s, c - 0.5 * s), 5 * s)
    pygame.draw.circle(d, shade(skin, 0.6), (c + 3 * s, c), 5.5 * s, s)
    # nombril
    pygame.draw.circle(d, shade(skin, 0.55), (c + 4 * s, c + s), 0.8 * s)
    # petits bras potelés
    for dy in (-9, 9):
        pygame.draw.circle(d, skin, (c + 3 * s, c + dy * s), 3 * s)
        pygame.draw.circle(d, shade(skin, 0.6), (c + 3 * s, c + dy * s), 3 * s, s)
    # grosse tête joufflue collée au corps
    pygame.draw.circle(d, shade(skin, 0.8), (c + 8 * s, c), 5 * s)
    pygame.draw.circle(d, skin, (c + 7.5 * s, c - 0.5 * s), 4.6 * s)
    # bouche grande ouverte, prête à dévorer
    pygame.draw.circle(d, (86, 34, 30), (c + 11 * s, c), 2.4 * s)
    pygame.draw.circle(d, (140, 60, 52), (c + 11 * s, c), 1.4 * s)
    pygame.draw.line(d, WHITE, (c + 9.6 * s, c - 1.8 * s), (c + 11.6 * s, c - 1.6 * s), s)
    # petits yeux gourmands
    for dy in (-2.6, 2.6):
        pygame.draw.circle(d, (32, 30, 36), (c + 9 * s, c + dy * s), 0.9 * s)
    # joues roses
    for dy in (-3.8, 3.8):
        pygame.draw.circle(d, (238, 160, 140), (c + 6.5 * s, c + dy * s), 1.2 * s)
    # touffe de cheveux
    pygame.draw.circle(d, (86, 56, 30), (c + 5 * s, c - 3.5 * s), 1.6 * s)


_PAINTERS = {"ouvrier": _paint_ouvrier, "soldat": _paint_soldat, "archer": _paint_archer,
             "mage": _paint_mage, "golem": _paint_golem, "baliste": _paint_baliste,
             "zombie": _paint_zombie, "maelan": _paint_maelan, "adryann": _paint_adryann}


def caca_sprite():
    """Petit tas marron à spirale laissé par Adryann, dessiné en 3x puis lissé."""
    key = ("caca",)
    if key not in ART:
        s = 3
        w, h = 14, 12
        d = pygame.Surface((w * s, h * s), pygame.SRCALPHA)
        brun = (118, 78, 40)
        # trois boules empilées
        pygame.draw.ellipse(d, shade(brun, 0.7), (2 * s, 7 * s, 10 * s, 4.6 * s))
        pygame.draw.ellipse(d, brun, (3.4 * s, 4.4 * s, 7.2 * s, 4.4 * s))
        pygame.draw.ellipse(d, lightc(brun, 0.15), (4.8 * s, 2.2 * s, 4.4 * s, 3.6 * s))
        # pointe en spirale
        pygame.draw.polygon(d, lightc(brun, 0.25), [(6.4 * s, 3 * s), (8.6 * s, 2.6 * s),
                                                    (7.6 * s, 0.8 * s)])
        # reflets
        pygame.draw.line(d, lightc(brun, 0.4), (4.4 * s, 8 * s), (6.4 * s, 8.4 * s), s)
        pygame.draw.line(d, lightc(brun, 0.4), (5 * s, 5.4 * s), (6.4 * s, 5.8 * s), s)
        ART[key] = pygame.transform.smoothscale(d, (w, h))
    return ART[key]


def tombstone_sprite():
    """Petite stèle grise, dessinée en 3x puis lissée."""
    key = ("tombstone",)
    if key not in ART:
        s = 3
        w, h = 18, 20
        d = pygame.Surface((w * s, h * s), pygame.SRCALPHA)
        st = (150, 152, 158)
        r = pygame.Rect(2 * s, 4 * s, 14 * s, 15 * s)
        pygame.draw.rect(d, shade(st, 0.55), r.move(s, s), border_radius=7 * s)
        pygame.draw.rect(d, st, r, border_radius=7 * s)
        pygame.draw.rect(d, shade(st, 0.5), r, s, border_radius=7 * s)
        pygame.draw.line(d, lightc(st, 0.35), (5 * s, 7 * s), (5 * s, 15 * s), s)
        # croix gravée
        pygame.draw.line(d, shade(st, 0.45), (9 * s, 8 * s), (9 * s, 14 * s), s)
        pygame.draw.line(d, shade(st, 0.45), (7 * s, 10 * s), (11 * s, 10 * s), s)
        # herbe au pied
        for gx in (3, 8, 13):
            pygame.draw.line(d, (74, 116, 58), (gx * s, 19 * s), (gx * s, 16 * s), s)
        ART[key] = pygame.transform.smoothscale(d, (w, h))
    return ART[key]


def unit_sprite(kind, pid):
    """Sprite de base, orienté vers la droite, lissé depuis un rendu 3x."""
    key = ("unit", kind, pid)
    if key not in ART:
        s = 3
        d = _unit_canvas(kind, s)
        _PAINTERS[kind](d, s, PLAYER_COLORS[pid])
        n = UNIT_CANVAS[kind]
        ART[key] = pygame.transform.smoothscale(d, (n, n))
    return ART[key]


def unit_frames(kind, pid):
    """16 orientations pré-calculées."""
    key = ("uframes", kind, pid)
    if key not in ART:
        base = unit_sprite(kind, pid)
        ART[key] = [pygame.transform.rotozoom(base, i * 22.5, 1.3) for i in range(16)]
    return ART[key]


def frame_index(facing):
    deg = math.degrees(math.atan2(-facing.y, facing.x))
    return int(round(deg / 22.5)) % 16


def brightened(surf):
    f = surf.copy()
    f.fill((85, 85, 85, 0), special_flags=pygame.BLEND_RGB_ADD)
    return f


# ------------------------------------------------------------- bâtiments
def _flag(d, x, y, s, col, flip=False):
    pygame.draw.line(d, (120, 118, 124), (x, y), (x, y - 14 * s), s)
    dx = -10 * s if flip else 10 * s
    pts = [(x, y - 14 * s), (x + dx, y - 11.5 * s), (x, y - 9 * s)]
    pygame.draw.polygon(d, col["main"], pts)
    pygame.draw.polygon(d, shade(col["main"], 0.55), pts, s)


def _window(d, x, y, w, h, s):
    pygame.draw.rect(d, (52, 40, 26), (x - s, y - s, w + 2 * s, h + 2 * s))
    vgrad(d, (x, y, w, h), (255, 214, 120), (200, 130, 40))


def _paint_qg(d, s, W, H, E, col):
    oy = E * s
    # plateforme de pierre
    plat = pygame.Rect(2 * s, oy + 24 * s, W * s - 4 * s, (H - 26) * s)
    vgrad(d, plat, (112, 106, 96), (68, 64, 58))
    pygame.draw.rect(d, (44, 42, 38), plat, s)
    bricks(d, plat.inflate(-4 * s, -4 * s), (86, 82, 74), 9 * s)
    # tours d'angle
    for tx, ty in [(15, 34), (W - 15, 34), (15, H - 15), (W - 15, H - 15)]:
        p = (tx * s, oy + ty * s)
        pygame.draw.circle(d, shade((116, 110, 100), 0.55), p, 12 * s)
        pygame.draw.circle(d, (116, 110, 100), (p[0] - 2 * s, p[1] - 2 * s), 10 * s)
        pygame.draw.circle(d, (44, 42, 38), p, 12 * s, s)
        pygame.draw.circle(d, col["dark"], p, 6 * s)
        pygame.draw.circle(d, col["main"], (p[0] - s, p[1] - s), 4 * s)
        for a in range(6):
            aa = a / 6 * math.tau
            pygame.draw.circle(d, (58, 55, 50),
                               (p[0] + math.cos(aa) * 10 * s, p[1] + math.sin(aa) * 10 * s), 1.6 * s)
    # donjon central
    keep = pygame.Rect(28 * s, oy + 8 * s, (W - 56) * s, (H - 44) * s)
    vgrad(d, keep, (132, 126, 114), (84, 80, 72))
    bricks(d, keep, (100, 95, 86), 8 * s)
    pygame.draw.rect(d, (46, 44, 40), keep, s)
    # toit trapèze aux couleurs de l'équipe
    roof = [(24 * s, oy + 10 * s), ((W - 24) * s, oy + 10 * s),
            ((W - 36) * s, oy - 12 * s), (36 * s, oy - 12 * s)]
    pygame.draw.polygon(d, col["main"], roof)
    pygame.draw.polygon(d, lightc(col["main"], 0.3),
                        [(24 * s, oy + 10 * s), (36 * s, oy - 12 * s),
                         (44 * s, oy - 12 * s), (36 * s, oy + 10 * s)])
    pygame.draw.polygon(d, shade(col["main"], 0.6),
                        [((W - 24) * s, oy + 10 * s), ((W - 36) * s, oy - 12 * s),
                         ((W - 44) * s, oy - 12 * s), ((W - 36) * s, oy + 10 * s)])
    pygame.draw.polygon(d, shade(col["dark"], 0.8), roof, s)
    pygame.draw.line(d, lightc(col["main"], 0.5), (36 * s, oy - 12 * s),
                     ((W - 36) * s, oy - 12 * s), s)
    # fenêtres
    for wx in (40, 58, W - 66, W - 48):
        _window(d, wx * s, oy + 22 * s, 6 * s, 9 * s, s)
    # porte
    g = pygame.Rect((W // 2 - 11) * s, oy + (H - 40) * s, 22 * s, 26 * s)
    pygame.draw.rect(d, (30, 26, 22), g)
    pygame.draw.rect(d, (78, 56, 34), g.inflate(-4 * s, -4 * s))
    for i in range(3):
        pygame.draw.line(d, (52, 38, 24), (g.x + 6 * s + i * 5 * s, g.y + 3 * s),
                         (g.x + 6 * s + i * 5 * s, g.bottom - 3 * s), s)
    pygame.draw.rect(d, (40, 34, 28), g, s)
    # bannières
    _flag(d, 24 * s, oy + (H - 20) * s, s, col)
    _flag(d, (W - 24) * s, oy + (H - 20) * s, s, col, flip=True)


def _paint_caserne(d, s, W, H, E, col):
    oy = E * s
    body = pygame.Rect(4 * s, oy + 14 * s, (W - 8) * s, (H - 16) * s)
    vgrad(d, body, (124, 118, 106), (76, 72, 64))
    bricks(d, body, (94, 90, 80), 9 * s)
    pygame.draw.rect(d, (44, 42, 38), body, s)
    # toit à double pente
    roof = [(0, oy + 16 * s), (W * s, oy + 16 * s), ((W - 14) * s, oy - 14 * s),
            (14 * s, oy - 14 * s)]
    pygame.draw.polygon(d, col["main"], roof)
    pygame.draw.polygon(d, lightc(col["main"], 0.28),
                        [(0, oy + 16 * s), (14 * s, oy - 14 * s), (26 * s, oy - 14 * s),
                         (14 * s, oy + 16 * s)])
    pygame.draw.polygon(d, shade(col["main"], 0.6),
                        [(W * s, oy + 16 * s), ((W - 14) * s, oy - 14 * s),
                         ((W - 26) * s, oy - 14 * s), ((W - 14) * s, oy + 16 * s)])
    pygame.draw.polygon(d, shade(col["dark"], 0.8), roof, s)
    pygame.draw.line(d, lightc(col["main"], 0.5), (14 * s, oy - 14 * s),
                     ((W - 14) * s, oy - 14 * s), 2 * s)
    # porte + enseigne épées croisées
    g = pygame.Rect((W // 2 - 9) * s, oy + (H - 26) * s, 18 * s, 24 * s)
    pygame.draw.rect(d, (30, 26, 22), g)
    pygame.draw.rect(d, (80, 58, 36), g.inflate(-4 * s, -4 * s))
    pygame.draw.rect(d, (40, 34, 28), g, s)
    pl = pygame.Rect((W // 2 - 8) * s, oy + 20 * s, 16 * s, 14 * s)
    pygame.draw.rect(d, (58, 50, 40), pl)
    pygame.draw.rect(d, (36, 32, 26), pl, s)
    pygame.draw.line(d, _METAL_L, (pl.x + 3 * s, pl.bottom - 3 * s),
                     (pl.right - 3 * s, pl.y + 3 * s), s)
    pygame.draw.line(d, _METAL_L, (pl.x + 3 * s, pl.y + 3 * s),
                     (pl.right - 3 * s, pl.bottom - 3 * s), s)
    # râtelier de lances
    for i in range(3):
        x = (10 + i * 6) * s
        pygame.draw.line(d, _WOOD, (x, oy + (H - 6) * s), (x + 3 * s, oy + 26 * s), s)
        pygame.draw.polygon(d, _METAL_L, [(x + 3 * s, oy + 26 * s), (x + s, oy + 30 * s),
                                          (x + 5 * s, oy + 30 * s)])
    _window(d, (W - 22) * s, oy + 26 * s, 7 * s, 9 * s, s)
    _flag(d, (W - 8) * s, oy + 6 * s, s, col, flip=True)


def _paint_archerie(d, s, W, H, E, col):
    oy = E * s
    body = pygame.Rect(4 * s, oy + 16 * s, (W - 8) * s, (H - 18) * s)
    vgrad(d, body, (118, 108, 92), (72, 66, 56))
    pygame.draw.rect(d, (44, 40, 34), body, s)
    # colombages
    for x in (14, 34, W - 34, W - 14):
        pygame.draw.line(d, (70, 52, 34), (x * s, body.y), (x * s, body.bottom), 2 * s)
    pygame.draw.line(d, (70, 52, 34), (body.x, oy + 30 * s), (body.right, oy + 30 * s), 2 * s)
    # toit pointu
    roof = [(0, oy + 18 * s), (W * s, oy + 18 * s), ((W // 2) * s, oy - 18 * s)]
    pygame.draw.polygon(d, shade(col["main"], 0.85), roof)
    pygame.draw.polygon(d, lightc(col["main"], 0.22),
                        [(0, oy + 18 * s), ((W // 2) * s, oy - 18 * s),
                         ((W // 2) * s, oy + 18 * s)])
    pygame.draw.polygon(d, shade(col["dark"], 0.8), roof, s)
    # cible
    cx, cy = (W // 2) * s, oy + 4 * s
    for r, c in ((7, (238, 234, 224)), (5, (210, 60, 50)), (3, (238, 234, 224)),
                 (1.4, (210, 60, 50))):
        pygame.draw.circle(d, c, (cx, cy), r * s)
    pygame.draw.circle(d, (60, 50, 40), (cx, cy), 7 * s, s)
    # porte + fenêtres en meurtrière
    g = pygame.Rect((W // 2 - 8) * s, oy + (H - 24) * s, 16 * s, 22 * s)
    pygame.draw.rect(d, (30, 26, 22), g)
    pygame.draw.rect(d, (80, 58, 36), g.inflate(-4 * s, -4 * s))
    pygame.draw.rect(d, (40, 34, 28), g, s)
    for x in (20, W - 24):
        pygame.draw.rect(d, (24, 22, 20), (x * s, oy + 34 * s, 3 * s, 10 * s))
    _flag(d, 8 * s, oy + 8 * s, s, col)


def _paint_forge(d, s, W, H, E, col):
    oy = E * s
    body = pygame.Rect(4 * s, oy + 12 * s, (W - 8) * s, (H - 14) * s)
    vgrad(d, body, (86, 78, 76), (48, 44, 44))
    bricks(d, body, (64, 58, 56), 10 * s)
    pygame.draw.rect(d, (30, 28, 28), body, s)
    # cheminée
    ch = pygame.Rect((W - 30) * s, oy - 16 * s, 16 * s, 34 * s)
    vgrad(d, ch, (96, 88, 84), (60, 54, 52))
    pygame.draw.rect(d, (32, 30, 30), ch, s)
    pygame.draw.ellipse(d, (30, 26, 26), (ch.x - s, ch.y - 3 * s, ch.w + 2 * s, 7 * s))
    pygame.draw.ellipse(d, (14, 12, 12), (ch.x + 2 * s, ch.y - s, ch.w - 4 * s, 4 * s))
    # gueule du four (la lueur est animée en jeu)
    m = pygame.Rect((W // 2 - 12) * s, oy + (H - 30) * s, 24 * s, 26 * s)
    pygame.draw.rect(d, (22, 18, 18), m, border_top_left_radius=12 * s,
                     border_top_right_radius=12 * s)
    pygame.draw.rect(d, (120, 50, 24), m.inflate(-6 * s, -6 * s),
                     border_top_left_radius=9 * s, border_top_right_radius=9 * s)
    # engrenage emblème
    gx, gy = 20 * s, oy + 26 * s
    for a in range(8):
        aa = a / 8 * math.tau
        pygame.draw.circle(d, _METAL, (gx + math.cos(aa) * 8 * s, gy + math.sin(aa) * 8 * s), 2 * s)
    pygame.draw.circle(d, _METAL, (gx, gy), 7 * s)
    pygame.draw.circle(d, shade(_METAL, 0.5), (gx, gy), 7 * s, s)
    pygame.draw.circle(d, (50, 46, 46), (gx, gy), 3 * s)
    # enclume
    pygame.draw.rect(d, (48, 48, 54), ((W - 34) * s, oy + (H - 16) * s, 14 * s, 5 * s))
    pygame.draw.rect(d, (70, 70, 78), ((W - 36) * s, oy + (H - 20) * s, 18 * s, 4 * s))
    _flag(d, 8 * s, oy + 2 * s, s, col)


def _paint_obelisque(d, s, W, H, E, col):
    oy = E * s
    # socle
    base = pygame.Rect(2 * s, oy + (H - 14) * s, (W - 4) * s, 12 * s)
    vgrad(d, base, (110, 104, 96), (66, 62, 56))
    pygame.draw.rect(d, (42, 40, 36), base, s)
    # monolithe de cristal teinté équipe
    cc = mix((96, 216, 255), col["main"], 0.30)
    cx = (W // 2) * s
    draw_shard(d, cx, oy + (H - 30) * s, 11 * s, (H - 6) * s * 0.62, cc)
    # runes (lueur animée en jeu)
    for i, ry in enumerate((-34, -22, -10)):
        pygame.draw.circle(d, lightc(cc, 0.6), (cx, oy + (H + ry) * s), 1.8 * s)


def _paint_tour(d, s, W, H, E, col):
    oy = E * s
    cx = (W // 2) * s
    stone = (122, 116, 106)
    # socle évasé
    base = pygame.Rect((W // 2 - 22) * s, oy + (H - 14) * s, 44 * s, 12 * s)
    vgrad(d, base, (108, 102, 92), (64, 60, 54))
    pygame.draw.rect(d, (42, 40, 36), base, s)
    # fût (vue de face, léger fuselage)
    body = [(cx - 17 * s, oy + (H - 12) * s), (cx + 17 * s, oy + (H - 12) * s),
            (cx + 13 * s, oy + 2 * s), (cx - 13 * s, oy + 2 * s)]
    pygame.draw.polygon(d, stone, body)
    shaft = pygame.Rect(cx - 15 * s, oy + 4 * s, 30 * s, (H - 18) * s)
    vgrad(d, shaft, lightc(stone, 0.16), shade(stone, 0.62))
    bricks(d, shaft, shade(stone, 0.75), 8 * s)
    pygame.draw.polygon(d, (44, 42, 38), body, s)
    pygame.draw.line(d, lightc(stone, 0.3), (cx - 12 * s, oy + 4 * s),
                     (cx - 15 * s, oy + (H - 14) * s), 2 * s)
    # bandeau couleur d'équipe
    band = pygame.Rect(cx - 14 * s, oy + 10 * s, 28 * s, 4 * s)
    pygame.draw.rect(d, col["main"], band)
    pygame.draw.rect(d, shade(col["dark"], 0.9), band, s)
    # meurtrière lumineuse
    pygame.draw.rect(d, (36, 30, 24), (cx - 2 * s, oy + 26 * s, 4 * s, 12 * s))
    vgrad(d, (cx - s, oy + 27 * s, 2 * s, 10 * s), (255, 214, 120), (200, 130, 40))
    # créneaux
    top = oy + 2 * s
    pygame.draw.rect(d, shade(stone, 0.8), (cx - 16 * s, top - 4 * s, 32 * s, 6 * s))
    pygame.draw.rect(d, (44, 42, 38), (cx - 16 * s, top - 4 * s, 32 * s, 6 * s), s)
    for i in range(4):
        mx = cx - 15 * s + i * 9 * s
        m = pygame.Rect(mx, top - 10 * s, 6 * s, 7 * s)
        vgrad(d, m, lightc(stone, 0.22), shade(stone, 0.8))
        pygame.draw.rect(d, (44, 42, 38), m, s)
    # socle de l'orbe (l'orbe flotte au-dessus, animé en jeu)
    pygame.draw.polygon(d, (70, 66, 60), [(cx - 5 * s, top - 10 * s),
                                          (cx + 5 * s, top - 10 * s),
                                          (cx + 2 * s, top - 16 * s),
                                          (cx - 2 * s, top - 16 * s)])
    _flag(d, cx + 15 * s, oy + 8 * s, s, col, flip=True)


def _paint_sanctuaire(d, s, W, H, E, col):
    oy = E * s
    stone = (124, 118, 108)
    # parvis de pierre
    base = pygame.Rect(2 * s, oy + 20 * s, (W - 4) * s, (H - 22) * s)
    vgrad(d, base, lightc(stone, 0.1), shade(stone, 0.6))
    bricks(d, base, shade(stone, 0.78), 8 * s)
    pygame.draw.rect(d, (44, 42, 38), base, s)
    # deux piliers + linteau (arche)
    for x in (10, W - 16):
        p = pygame.Rect(x * s, oy - 8 * s, 6 * s, 32 * s)
        vgrad(d, p, lightc(stone, 0.25), shade(stone, 0.65))
        pygame.draw.rect(d, (44, 42, 38), p, s)
    lin = pygame.Rect(8 * s, oy - 14 * s, (W - 16) * s, 7 * s)
    vgrad(d, lin, lightc(stone, 0.3), shade(stone, 0.7))
    pygame.draw.rect(d, (44, 42, 38), lin, s)
    pygame.draw.rect(d, col["main"], (lin.x + 2 * s, lin.y + 2 * s, lin.w - 4 * s, 2 * s))
    # autel central
    alt = pygame.Rect((W // 2 - 8) * s, oy + 26 * s, 16 * s, 12 * s)
    vgrad(d, alt, lightc(stone, 0.2), shade(stone, 0.55))
    pygame.draw.rect(d, (44, 42, 38), alt, s)
    # épée dressée sur l'autel
    cx = (W // 2) * s
    pygame.draw.line(d, _METAL_L, (cx, oy + 26 * s), (cx, oy + 2 * s), 2 * s)
    pygame.draw.line(d, WHITE, (cx - s, oy + 24 * s), (cx - s, oy + 6 * s), s)
    pygame.draw.line(d, (206, 172, 84), (cx - 5 * s, oy + 22 * s), (cx + 5 * s, oy + 22 * s), 2 * s)
    pygame.draw.polygon(d, _METAL_L, [(cx, oy - 2 * s), (cx - 2 * s, oy + 3 * s),
                                      (cx + 2 * s, oy + 3 * s)])
    # bouclier appuyé contre l'autel
    sh = pygame.Rect(0, 0, 10 * s, 13 * s)
    sh.center = (cx - 12 * s, oy + 36 * s)
    pygame.draw.ellipse(d, col["dark"], sh)
    pygame.draw.ellipse(d, lightc(col["main"], 0.25), sh.inflate(-3 * s, -3 * s))
    pygame.draw.ellipse(d, shade(col["dark"], 0.6), sh, s)
    # braseros aux coins
    for x in (8, W - 8):
        pygame.draw.line(d, (70, 62, 52), (x * s, oy + (H - 6) * s),
                         (x * s, oy + (H - 16) * s), 2 * s)
        pygame.draw.circle(d, (255, 190, 90), (x * s, oy + (H - 18) * s), 2.6 * s)
        pygame.draw.circle(d, (255, 240, 180), (x * s, oy + (H - 19) * s), 1.2 * s)
    _flag(d, (W - 6) * s, oy + 10 * s, s, col, flip=True)


def _paint_muraille(d, s, W, H, E, col):
    oy = E * s
    stone = (118, 112, 102)
    # mur plein (pas de contour latéral : les segments se raccordent)
    body = pygame.Rect(0, oy - 8 * s, W * s, (H + 8) * s)
    vgrad(d, body, lightc(stone, 0.16), shade(stone, 0.55))
    bricks(d, body, shade(stone, 0.75), 8 * s)
    # créneaux
    for i in range(2):
        m = pygame.Rect((3 + i * 16) * s, oy - 14 * s, 10 * s, 8 * s)
        vgrad(d, m, lightc(stone, 0.26), shade(stone, 0.8))
        pygame.draw.rect(d, (44, 42, 38), m, s)
    pygame.draw.line(d, (44, 42, 38), (0, oy - 8 * s), (W * s, oy - 8 * s), s)
    pygame.draw.line(d, lightc(stone, 0.3), (0, oy - 6 * s), (W * s, oy - 6 * s), s)
    pygame.draw.line(d, (44, 42, 38), (0, body.bottom - s), (W * s, body.bottom - s), s)


def _paint_porte(d, s, W, H, E, col, open_=False):
    oy = E * s
    stone = (118, 112, 102)
    # passage (sol sombre visible quand la porte est ouverte)
    if open_:
        pygame.draw.rect(d, (72, 62, 48), (4 * s, oy + 2 * s, (W - 8) * s, (H - 4) * s))
        pygame.draw.rect(d, (56, 48, 38), (4 * s, oy + 2 * s, (W - 8) * s, (H - 4) * s), s)
    # piliers latéraux
    for x in (0, W - 7):
        p = pygame.Rect(x * s, oy - 12 * s, 7 * s, (H + 12) * s)
        vgrad(d, p, lightc(stone, 0.22), shade(stone, 0.6))
        pygame.draw.rect(d, (44, 42, 38), p, s)
    # linteau
    lin = pygame.Rect(0, oy - 12 * s, W * s, 7 * s)
    vgrad(d, lin, lightc(stone, 0.3), shade(stone, 0.7))
    pygame.draw.rect(d, (44, 42, 38), lin, s)
    pygame.draw.rect(d, col["main"], (lin.x + 2 * s, lin.y + 2 * s, lin.w - 4 * s, 2 * s))
    if not open_:
        # double battant de bois avec renforts
        door = pygame.Rect(6 * s, oy - 4 * s, (W - 12) * s, (H + 2) * s)
        vgrad(d, door, (110, 80, 48), (72, 52, 32))
        pygame.draw.line(d, (48, 36, 24), (door.centerx, door.y), (door.centerx, door.bottom), s)
        for j in (door.y + 4 * s, door.centery, door.bottom - 4 * s):
            pygame.draw.line(d, (58, 56, 60), (door.x + s, j), (door.right - s, j), s)
        pygame.draw.rect(d, (40, 34, 28), door, s)
        for dx in (-3, 3):
            pygame.draw.circle(d, (30, 26, 22), (door.centerx + dx * s, door.centery), s)
    else:
        # battants entrouverts contre les piliers
        for x, flip in ((7 * s, 1), ((W - 7) * s, -1)):
            pygame.draw.polygon(d, (96, 70, 42),
                                [(x, oy - 4 * s), (x + flip * 4 * s, oy - 2 * s),
                                 (x + flip * 4 * s, oy + (H - 2) * s), (x, oy + H * s)])


def _paint_porte_open(d, s, W, H, E, col):
    _paint_porte(d, s, W, H, E, col, open_=True)


_BPAINT = {"qg": _paint_qg, "caserne": _paint_caserne, "archerie": _paint_archerie,
           "forge": _paint_forge, "obelisque": _paint_obelisque, "tour": _paint_tour,
           "sanctuaire": _paint_sanctuaire, "muraille": _paint_muraille,
           "porte": _paint_porte, "porte_open": _paint_porte_open}
BUILDING_PX = {"qg": (128, 96), "caserne": (96, 64), "archerie": (96, 64),
               "forge": (96, 96), "obelisque": (32, 64), "tour": (64, 64),
               "sanctuaire": (64, 64), "muraille": (32, 32), "porte": (32, 32),
               "porte_open": (32, 32)}


def building_sprite(kind, pid):
    key = ("bld", kind, pid)
    if key not in ART:
        W, H = BUILDING_PX[kind]
        s = 2
        d = pygame.Surface((W * s, (H + BUILD_EXT) * s), pygame.SRCALPHA)
        _BPAINT[kind](d, s, W, H, BUILD_EXT, PLAYER_COLORS[pid])
        ART[key] = pygame.transform.smoothscale(d, (W, H + BUILD_EXT))
    return ART[key]


# --------------------------------------------------------------- décor
def tree_sprite(seed):
    key = ("tree", seed % 5)
    if key not in ART:
        rng = random.Random(seed % 5)
        s = 2
        d = pygame.Surface((48 * s, 56 * s), pygame.SRCALPHA)
        cx, base = 24 * s, 50 * s
        # tronc
        pygame.draw.polygon(d, (74, 52, 34), [(cx - 3 * s, base), (cx + 3 * s, base),
                                              (cx + 2 * s, base - 14 * s),
                                              (cx - 2 * s, base - 14 * s)])
        pygame.draw.line(d, (52, 36, 24), (cx - 2 * s, base), (cx - s, base - 12 * s), s)
        # feuillage en 3 couches
        blobs = [(0, -20, 15, (36, 74, 40)), (-5, -26, 11, (48, 96, 50)),
                 (5, -24, 10, (44, 88, 46)), (-1, -32, 8, (62, 118, 60))]
        for dx, dy, r, c in blobs:
            j = rng.randint(-2, 2)
            pygame.draw.circle(d, shade(c, 0.55), (cx + (dx + j) * s, (56 + dy) * s + base - 56 * s), (r + 1) * s)
            pygame.draw.circle(d, c, (cx + (dx + j - 1) * s, (55 + dy) * s + base - 56 * s), r * s)
        for _ in range(14):
            a = rng.uniform(0, math.tau)
            rr = rng.uniform(2, 12)
            pygame.draw.circle(d, (86, 148, 78),
                               (cx + math.cos(a) * rr * s, base - 26 * s + math.sin(a) * rr * s * 0.7),
                               1.2 * s)
        ART[key] = pygame.transform.smoothscale(d, (48, 56))
    return ART[key]


def rock_sprite(seed):
    key = ("rock", seed % 4)
    if key not in ART:
        rng = random.Random(seed % 4 + 11)
        s = 2
        d = pygame.Surface((30 * s, 24 * s), pygame.SRCALPHA)
        pts = []
        for i in range(7):
            a = i / 7 * math.tau
            r = (9 + rng.uniform(-2, 3)) * s
            pts.append((15 * s + math.cos(a) * r, 13 * s + math.sin(a) * r * 0.7))
        pygame.draw.polygon(d, (108, 108, 114), pts)
        pygame.draw.polygon(d, (140, 140, 148),
                            [(p[0] - 2 * s, p[1] - 2 * s) for p in pts[:4]])
        pygame.draw.polygon(d, (62, 62, 68), pts, s)
        ART[key] = pygame.transform.smoothscale(d, (30, 24))
    return ART[key]


# --------------------------------------------------------------- terrain
def make_terrain(world_w, world_h, tile, seed=7):
    rng = random.Random(seed)
    mw, mh = world_w // tile, world_h // tile
    bg = pygame.Surface((world_w, world_h))
    # bruit de valeur bilinéaire, 2 octaves
    g1 = [[rng.random() for _ in range(mw // 4 + 3)] for _ in range(mh // 4 + 3)]
    g2 = [[rng.random() for _ in range(mw // 2 + 3)] for _ in range(mh // 2 + 3)]

    def sample(grid, x, y, cell):
        gx, gy = x / cell, y / cell
        x0, y0 = int(gx), int(gy)
        fx, fy = gx - x0, gy - y0
        a = grid[y0][x0] * (1 - fx) + grid[y0][x0 + 1] * fx
        b = grid[y0 + 1][x0] * (1 - fx) + grid[y0 + 1][x0 + 1] * fx
        return a * (1 - fy) + b * fy

    dark = (58, 94, 50)
    lightg = (98, 136, 68)
    dry = (120, 128, 68)
    sub = tile // 2
    for sy in range(mh * 2):
        for sx in range(mw * 2):
            n = 0.62 * sample(g1, sx / 2, sy / 2, 4) + 0.38 * sample(g2, sx / 2, sy / 2, 2)
            n = clamp(n + rng.uniform(-0.05, 0.05), 0, 1)
            col = mix(dark, lightg, n)
            if n > 0.72:
                col = mix(col, dry, (n - 0.72) * 2.2)
            r = pygame.Rect(sx * sub, sy * sub, sub, sub)
            bg.fill(col, r)
            speckle(bg, r, rng, 3, 8)
    # grandes variations douces pour casser la grille
    for _ in range(46):
        rr = rng.randint(60, 190)
        lay = pygame.Surface((rr * 2, rr * 2), pygame.SRCALPHA)
        col = rng.choice([(28, 58, 32, 9), (126, 156, 84, 8), (40, 80, 40, 8)])
        for i in range(rr, 0, -6):
            pygame.draw.circle(lay, col, (rr, rr), i)
        bg.blit(lay, (rng.randint(-rr, world_w - rr), rng.randint(-rr, world_h - rr)))
    # touffes d'herbe
    for _ in range(1600):
        x, y = rng.randint(2, world_w - 3), rng.randint(4, world_h - 3)
        c = bg.get_at((x, y))
        gc = shade((c[0], c[1], c[2]), rng.choice([0.75, 1.3]))
        for k in range(3):
            pygame.draw.line(bg, gc, (x + k * 2 - 2, y),
                             (x + k * 2 - 2 + rng.randint(-1, 1), y - rng.randint(2, 5)))
    # fleurs
    for _ in range(240):
        x, y = rng.randint(0, world_w - 1), rng.randint(0, world_h - 1)
        pygame.draw.circle(bg, rng.choice([(220, 220, 240), (235, 210, 120),
                                           (150, 210, 240)]), (x, y), 1)
    # cailloux
    for _ in range(160):
        x, y = rng.randint(0, world_w - 4), rng.randint(0, world_h - 4)
        pygame.draw.circle(bg, (116, 116, 120), (x, y), rng.randint(1, 2))
        pygame.draw.circle(bg, (80, 80, 86), (x + 1, y + 1), 1)
    return bg


def bake_plaza(bg, cx, cy, r, seed=3):
    rng = random.Random(seed)
    lay = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    for i in range(r, 0, -2):
        a = 140 if i < r - 14 else int(140 * (r - i) / 14)
        pygame.draw.circle(lay, (96, 88, 74, a), (r, r), i)
    for _ in range(int(r * r / 40)):
        aa = rng.uniform(0, math.tau)
        rr = rng.uniform(0, r - 6)
        p = (r + math.cos(aa) * rr, r + math.sin(aa) * rr)
        c = rng.choice([(108, 100, 84), (88, 80, 68), (118, 110, 94)])
        pygame.draw.circle(lay, c + (220,), p, rng.randint(2, 4))
    pygame.draw.circle(lay, (60, 54, 46, 160), (r, r), r - 1, 2)
    bg.blit(lay, (cx - r, cy - r))


def bake_path(bg, p0, p1, seed=5):
    rng = random.Random(seed)
    x0, y0 = p0
    x1, y1 = p1
    L = math.hypot(x1 - x0, y1 - y0)
    n = int(L / 9)
    for i in range(n + 1):
        t = i / n
        # légère sinuosité
        sx = x0 + (x1 - x0) * t + math.sin(t * 9) * 42 + rng.uniform(-6, 6)
        sy = y0 + (y1 - y0) * t + math.cos(t * 7) * 34 + rng.uniform(-6, 6)
        r = rng.randint(9, 15)
        lay = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(lay, (104, 94, 70, 70), (r, r), r)
        pygame.draw.circle(lay, (94, 84, 62, 60), (r, r), int(r * 0.6))
        bg.blit(lay, (sx - r, sy - r))


# ------------------------------------------------------------------- UI
def panel_img(w, h, gems=True):
    key = ("panel", w, h, gems)
    if key not in ART:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        vgrad(s, (0, 0, w, h), (52, 58, 74), (26, 30, 40))
        # texture légère
        rng = random.Random(2)
        for _ in range(w * h // 160):
            x, y = rng.randint(2, w - 3), rng.randint(2, h - 3)
            c = s.get_at((x, y))
            d = rng.randint(-6, 6)
            s.set_at((x, y), (clamp(c[0] + d, 0, 255), clamp(c[1] + d, 0, 255),
                              clamp(c[2] + d, 0, 255), 255))
        pygame.draw.rect(s, (10, 12, 16), (0, 0, w, h), 2)
        pygame.draw.line(s, (96, 108, 132), (2, 2), (w - 3, 2))
        pygame.draw.line(s, (96, 108, 132), (2, 2), (2, h - 3))
        pygame.draw.line(s, (14, 16, 22), (2, h - 3), (w - 3, h - 3))
        pygame.draw.line(s, (14, 16, 22), (w - 3, 2), (w - 3, h - 3))
        if gems:
            for gx, gy in ((10, 10), (w - 10, 10), (10, h - 10), (w - 10, h - 10)):
                draw_shard(s, gx, gy, 5, 7, (100, 220, 255))
        ART[key] = s
    return ART[key]


def button_img(w, h, state):
    """state: 0 normal, 1 survolé, 2 désactivé"""
    key = ("btn", w, h, state)
    if key not in ART:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        if state == 2:
            vgrad(s, (0, 0, w, h), (44, 47, 56), (32, 34, 42))
            pygame.draw.rect(s, (20, 22, 28), (0, 0, w, h), 1, border_radius=5)
        else:
            top = (86, 96, 120) if state == 1 else (68, 76, 98)
            bot = (40, 46, 60) if state == 1 else (34, 38, 50)
            vgrad(s, (0, 0, w, h), top, bot)
            pygame.draw.rect(s, (12, 14, 18), (0, 0, w, h), 1, border_radius=5)
            pygame.draw.line(s, lightc(top, 0.3), (2, 1), (w - 3, 1))
            if state == 1:
                pygame.draw.rect(s, (110, 220, 255), (0, 0, w, h), 1, border_radius=5)
        ART[key] = s
    return ART[key]


def icon_crystal(size):
    key = ("icoc", size)
    if key not in ART:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        draw_shard(s, size // 2, size // 2 + size // 6, size * 0.42, size * 0.46, (96, 216, 255))
        ART[key] = s
    return ART[key]


def icon_supply(size):
    key = ("icos", size)
    if key not in ART:
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        m = size // 2
        pygame.draw.polygon(s, (210, 190, 120), [(m, 2), (size - 2, m), (2, m)])
        pygame.draw.rect(s, (180, 160, 100), (m - size // 4, m, size // 2, size // 2 - 2))
        pygame.draw.rect(s, (60, 50, 30), (m - size // 4, m, size // 2, size // 2 - 2), 1)
        ART[key] = s
    return ART[key]


def icon_unit(kind, pid, size):
    key = ("icou", kind, pid, size)
    if key not in ART:
        ART[key] = pygame.transform.smoothscale(unit_sprite(kind, pid), (size, size))
    return ART[key]


def icon_upgrade(kind, size):
    key = ("icoup", kind, size)
    if key not in ART:
        z = size
        s = pygame.Surface((z, z), pygame.SRCALPHA)
        if kind == "up_atq":
            # épée en diagonale
            w = max(2, z // 7)
            pygame.draw.line(s, _METAL_L, (z * 0.28, z * 0.72), (z * 0.80, z * 0.20), w)
            pygame.draw.line(s, WHITE, (z * 0.36, z * 0.60), (z * 0.74, z * 0.22),
                             max(1, w // 2))
            pygame.draw.line(s, (206, 172, 84), (z * 0.20, z * 0.58), (z * 0.40, z * 0.78),
                             max(2, w - 1))
            pygame.draw.line(s, (140, 104, 62), (z * 0.14, z * 0.86), (z * 0.28, z * 0.72), w)
        else:
            # bouclier
            pts = [(z * 0.5, z * 0.08), (z * 0.86, z * 0.24), (z * 0.78, z * 0.62),
                   (z * 0.5, z * 0.92), (z * 0.22, z * 0.62), (z * 0.14, z * 0.24)]
            pygame.draw.polygon(s, (86, 128, 196), pts)
            pygame.draw.polygon(s, (150, 190, 240),
                                [(z * 0.5, z * 0.16), (z * 0.5, z * 0.84),
                                 (z * 0.28, z * 0.58), (z * 0.22, z * 0.28)])
            pygame.draw.polygon(s, (26, 38, 66), pts, max(1, z // 12))
            pygame.draw.circle(s, (120, 226, 255), (z * 0.5, z * 0.42), z * 0.08)
        ART[key] = s
    return ART[key]


def icon_building(kind, pid, size):
    key = ("icob", kind, pid, size)
    if key not in ART:
        sp = building_sprite(kind, pid)
        w, h = sp.get_size()
        f = size / max(w, h)
        ART[key] = pygame.transform.smoothscale(sp, (max(1, int(w * f)), max(1, int(h * f))))
    return ART[key]
