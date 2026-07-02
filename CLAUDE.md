# CRISTALIS — La Guerre des Cristaux

RTS 2D en pygame, en français. Récolte de cristaux, construction de base, armée, destruction de la base ennemie. Solo contre IA ou multijoueur LAN.

## Lancement et tests

- Python du projet : `venv/bin/python` (Python 3.12, pygame 2.6.1, numpy). Toujours utiliser ce venv.
- Jouer : `venv/bin/python cristalis.py` (ou `./run.sh`)
- Test auto sans fenêtre (IA vs IA, ~45 min simulées) : `venv/bin/python cristalis.py --autotest`
- Smoke test rendu headless (240 frames) : `CRISTALIS_SMOKE=1 venv/bin/python cristalis.py`
- Test lockstep 2 processus : scripts `mp_sim.py host|join` dans le scratchpad (comparer les `state_hash` host/join entre eux ; ils varient d'une exécution à l'autre, artefact du script).

## Fichiers

- `cristalis.py` — tout le jeu : données (UNIT_TYPES, BUILDING_TYPES, DIFFICULTES, GameConfig), entités (Unit, Building, Crystal, Doodad, Projectile), IA (AIController), simulation + rendu + entrées (Game), menus (MenuUI + fonctions `menu`, `pick_difficulty`, `game_options`…), boucles (`run_solo`, `run_multiplayer`, `main`).
- `art.py` — sprites 100 % procéduraux (unités, bâtiments, terrain, UI). Cache global `ART`. `PLAYER_COLORS` indexé par pid.
- `netcode.py` — TCP JSON ligne par ligne (`Peer`), découverte UDP (`HostListener`, `Discovery`).
- `DEVLOG.md` — journal de développement. **RÈGLE : mettre à jour DEVLOG.md à chaque modification du code** (date, quoi, pourquoi, comment testé).

## Invariants critiques (multijoueur lockstep)

Le LAN est en lockstep déterministe : les deux machines simulent la même partie (seed partagée, `TICK_DT = 1/20`, commandes exécutées à `tick + NET_DELAY`). `state_hash()` est comparé toutes les 100 ticks pour détecter les désyncs.

1. **Toute action de joueur passe par `Game.issue()` / `apply_command()`** — jamais de mutation directe de la simulation depuis les entrées ou le HUD.
2. **Le code de simulation ne doit consommer le RNG global (`random`) que de façon identique des deux côtés.** Pas de `random` dans du code qui dépend de l'état local (sélection, caméra, brouillard, sons). Le rendu peut utiliser `random.Random(seed_local)`.
3. **Le brouillard de guerre est purement visuel/local** — jamais dans `state_hash`, jamais consulté par la simulation.
4. Les options de partie (vitesse, zombies, taille de map) doivent être identiques des deux côtés : l'hôte les envoie dans le message `hello` avec la seed.
5. Le pathfinding et toute nouvelle logique de sim doivent être déterministes (tri stable, tie-break par uid, pas de `dict` non ordonné itéré pour des décisions).

## Conventions

- Code et textes de jeu en **français** (l'utilisateur écrit en français, style décontracté).
- Un seul gros fichier par couche, sections séparées par des bannières `# ---- nom`.
- Constantes de données en dicts en tête de fichier (`UNIT_TYPES`…), pas de classes de config.
- Sprites : jamais de fichiers image, tout est peint dans `art.py` et mis en cache dans `ART`.
- `pid` 0/1 = joueurs, `pid` 2 = zombies (joueur neutre hostile, jamais dans la condition de victoire).

## Pièges connus

- `SCREEN_W/H` sont fixes (1280×720) ; le plein écran passe par `pygame.SCALED`, ne pas changer la résolution logique.
- `MAP_W/MAP_H/WORLD_W/WORLD_H` sont des globales modifiées par `set_map_size()` **avant** de créer `Game` — toujours relire ces globales, ne pas les capturer à l'import.
- La condition de victoire ne regarde que les joueurs 0 et 1 (les zombies n'ont pas de bâtiments).
- `Building._next_id` / `Unit._next_id` sont réinitialisés dans `Game.__init__` (nécessaire au lockstep).
