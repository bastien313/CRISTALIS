# -*- coding: utf-8 -*-
"""
CRISTALIS — données et constantes d'équilibrage.
Aucune logique de jeu ici : dicts de données, constantes d'écran, config de
partie par défaut. Ce module doit être importé avant pygame : il pose
SDL_VIDEODRIVER=dummy pour les modes headless (--autotest, CRISTALIS_SMOKE).
"""

import math
import os
import sys

AUTOTEST = "--autotest" in sys.argv
SMOKE = os.environ.get("CRISTALIS_SMOKE") == "1"
if AUTOTEST or SMOKE:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

# Compteur de version : à incrémenter à chaque modification du code.
# Affiché au démarrage (menu + titre de fenêtre).
VERSION = "0.18"

TILE = 32
# clé -> (nom affiché, largeur en cases, hauteur en cases, joueurs max)
# Le fond est généré chunk par chunk (art.Terrain, cache LRU borné) : la
# taille de carte ne pèse plus sur la RAM. Restent proportionnels à la carte :
# brouillard (2 octets/case), grille A*, surface de brouillard minimap.
MAP_SIZES = {"petite": ("Petite", 96, 68, 2),
             "moyenne": ("Moyenne", 128, 88, 4),
             "grande": ("Grande", 192, 128, 8),
             "geante": ("Géante", 512, 256, 8)}
SCREEN_W, SCREEN_H = 1280, 720
HUD_H = 170
VIEW_W, VIEW_H = SCREEN_W, SCREEN_H - HUD_H
TOPBAR_H = 30
EDGE_SCROLL = 18
CAM_SPEED = 520

# Multijoueur : simulation à pas fixe, les commandes émises au tick T
# sont exécutées au tick T + net_delay sur les deux machines. NET_DELAY est
# la valeur par défaut/minimale ; l'hôte peut en choisir une plus grande au
# handshake selon le RTT mesuré (netcode.pick_net_delay) — identique des
# deux côtés, lockstep préservé.
TICK_DT = 1 / 20
NET_DELAY = 3
# Keepalive applicatif : battement émis toutes les KA_INTERVAL s ; pair
# déclaré perdu après KA_TIMEOUT s sans rien recevoir (une connexion
# Internet peut mourir en silence, TCP ne le signale qu'après des minutes).
KA_INTERVAL = 2.0
KA_TIMEOUT = 10.0

MAX_PLAYERS = 8
ZOMBIE_PID = 8     # pid réservé au joueur neutre zombie (couleur 9 de art.py)
ZOMBIE_TEAM = 99   # équipe à part : hostile à tout le monde
TOMB_DELAY = 20.0  # secondes entre la mort d'une unité et le zombie

# Options de partie : identiques des deux côtés en LAN (l'hôte les envoie au
# client avec la seed dans le message "hello"). `players` contient un slot par
# joueur (2 à 8) : ai (bool) et team (1..8). En LAN les slots 0 et 1 sont
# humains, en solo seul le slot 0 l'est.
DEFAULT_CONFIG = dict(speed=1, zombies=False, map="moyenne",
                      zombie_spawn_interval=60, zombie_invasion_delay=120,
                      players=[dict(ai=False, team=1), dict(ai=True, team=2)])

C_TEXT = (226, 230, 238)
C_DIM = (148, 156, 172)
C_CRYSTAL = (96, 220, 255)
C_GOOD = (118, 224, 128)
C_BAD = (238, 96, 84)
C_GOLD = (238, 210, 120)

FACTION_NAMES = ["Ordre d'Azur", "Légion Karmin", "Pacte d'Émeraude",
                 "Conclave Améthyste", "Horde Ambrée", "Clan Églantine",
                 "Marée Turquoise", "Dynastie Dorée"]
AI_NAMES = ["Seigneur Vhrax", "Générale Onyx", "Archonte Malgrim"]

# ------------------------------------------------------------------- unités
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
    # unités d'élite de la caserne (cadence : Maelan 1,7 coups/s, Adryann 1/s)
    "maelan": dict(nom="Maelan", cout=450, hp=200, degats=20, portee=20, vitesse=100,
                   cooldown=0.6, supply=3, rayon=9, tps=15.0, aggro=170, splash=0,
                   desc="Petit ninja d'élite : rapide comme le vent, frappe sans répit."),
    "adryann": dict(nom="Adryann", cout=420, hp=200, degats=20, portee=20, vitesse=60,
                    cooldown=1.0, supply=3, rayon=12, tps=16.0, aggro=160, splash=0,
                    desc="Bouboule vorace : dévore ses victimes (+10% PV)… et sème "
                         "des petits cadeaux."),
}

# ---------------------------------------------------------------- bâtiments
BUILDING_TYPES = {
    "qg": dict(nom="Quartier Général", cout=400, hp=950, taille=(4, 3), supply=10,
               prod=["ouvrier"], build_time=45, depot=True, degats=0, portee=0, cooldown=0,
               desc="Cœur de la base : produit les ouvriers, reçoit les cristaux."),
    "obelisque": dict(nom="Obélisque", cout=100, hp=260, taille=(1, 2), supply=8,
                      prod=[], build_time=13, depot=False, degats=0, portee=0, cooldown=0,
                      desc="Canalise l'énergie : +8 de ravitaillement."),
    "caserne": dict(nom="Caserne", cout=150, hp=550, taille=(3, 2), supply=0,
                    prod=["soldat", "maelan", "adryann"], build_time=20, depot=False,
                    degats=0, portee=0, cooldown=0,
                    desc="Forme les soldats de mêlée et les champions Maelan et Adryann."),
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
                  desc="Ne s'ouvre que pour laisser passer votre équipe."),
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
                "maelan": pygame.K_n, "adryann": pygame.K_y,
                "up_atq": pygame.K_a, "up_def": pygame.K_d}

# tempo : divise l'horloge du plan de construction de l'IA (plus grand = plus lent)
# wave_max : taille maximale des vagues d'attaque de l'IA
DIFFICULTES = {
    "facile": dict(nom="Facile", income=0.55, workers=6, wave0=4, wave_step=1,
                   prod_pause=10.0, tempo=1.9, wave_max=10,
                   desc="L'IA prend vraiment son temps. Idéal pour apprendre."),
    "normal": dict(nom="Normal", income=1.0, workers=12, wave0=8, wave_step=2,
                   prod_pause=2.5, tempo=1.0, wave_max=22,
                   desc="Un adversaire équilibré."),
    "difficile": dict(nom="Difficile", income=1.35, workers=18, wave0=10, wave_step=3,
                      prod_pause=0.0, tempo=0.85, wave_max=30,
                      desc="L'IA est agressive et efficace. Bonne chance."),
    "survie": dict(nom="Survie zombie", income=1.0, workers=0, wave0=0, wave_step=0,
                    prod_pause=0.0, tempo=1.0, wave_max=0,
                    desc="Tenez le plus longtemps possible face à l'invasion."),
}


def dist_point_rect(p, rect):
    cx = min(max(p.x, rect.left), rect.right)
    cy = min(max(p.y, rect.top), rect.bottom)
    return math.hypot(p.x - cx, p.y - cy)
