# CRISTALIS — La Guerre des Cristaux

RTS 2D en pygame, en français. Récolte de cristaux, construction de base, armée, destruction des bases ennemies. Solo contre IA (2 à 8 joueurs, équipes) ou multijoueur LAN.

## Lancement et tests

- Python du projet : `venv/bin/python` (Python 3.12, pygame 2.6.1, numpy). Toujours utiliser ce venv.
- Jouer : `venv/bin/python cristalis.py` (ou `./run.sh`)
- Test auto sans fenêtre (IA vs IA) : `venv/bin/python cristalis.py --autotest`
- Smoke test rendu headless (240 frames) : `CRISTALIS_SMOKE=1 venv/bin/python cristalis.py`
- Suite de tests headless + test lockstep 2 processus : scripts `test_features.py` et `mp_sim.py host|join` dans le scratchpad (les `state_hash` host/join doivent être égaux entre eux ; ils varient d'une exécution à l'autre, artefact du script).

## Architecture (un module par couche)

- `cristalis.py` — point d'entrée : boucles `run_solo`, `run_multiplayer`, `run_autotest`, `main`. Réexporte Game/constantes pour les scripts de test.
- `data.py` — constantes et dicts d'équilibrage (UNIT_TYPES, BUILDING_TYPES, DIFFICULTES, MAP_SIZES, DEFAULT_CONFIG…). **Importé en premier** : pose SDL_VIDEODRIVER=dummy pour les modes headless avant l'import de pygame.
- `entities.py` — Player (avec `team`), Doodad, Crystal, Building, Unit (pathfinding, `build_queue`), Projectile. Les entités ne touchent ni au réseau ni aux entrées : tout passe par `game`.
- `ia.py` — AIController (un par joueur IA, cible toute équipe ennemie).
- `game.py` — classe `Game` (hérite de RenderMixin) : simulation, commandes lockstep, pathfinding A*, brouillard, victoire par équipe, entrées. Aussi `sanitize_config` et `build_sounds`.
- `render.py` — `RenderMixin` : tout le dessin en jeu (monde, HUD, vignettes de sélection, minimap, brouillard, aide, fin). Ne modifie jamais la sim.
- `menus.py` — MenuUI, écrans (menu, difficulté, `game_options` joueurs/équipes/vitesse/zombies/carte, LAN), `global_key` (F11).
- `art.py` — sprites 100 % procéduraux. Cache global `ART`. `PLAYER_COLORS` : 8 factions (pid 0..7) + zombies (pid 8).
- `netcode.py` — TCP JSON ligne par ligne (`Peer`), découverte UDP.
- `DEVLOG.md` — journal de développement. **RÈGLE : mettre à jour DEVLOG.md à chaque modification du code** (date, quoi, pourquoi, comment testé).

## Invariants critiques (multijoueur lockstep)

Le LAN est en lockstep déterministe : les deux machines simulent la même partie (seed partagée, `TICK_DT = 1/20`, commandes exécutées à `tick + NET_DELAY`). `state_hash()` est comparé toutes les 100 ticks.

1. **Toute action de joueur passe par `Game.issue()` / `apply_command()`** — jamais de mutation directe de la simulation depuis les entrées ou le HUD.
2. **Le code de simulation ne doit consommer le RNG global (`random`) que de façon identique des deux côtés.** Pas de `random` dans du code dépendant de l'état local (sélection, caméra, brouillard, sons). Le rendu peut utiliser `random.Random(seed_local)`.
3. **Le brouillard de guerre est purement visuel/local** — jamais dans `state_hash`, jamais consulté par la simulation. Il révèle la vision de toute l'équipe du joueur local.
4. La config de partie (vitesse, zombies, taille de map, slots joueurs/équipes) est envoyée par l'hôte dans `hello` avec la seed : identique des deux côtés.
5. **Les IA tournent aussi en LAN** (slots 2+) : elles font partie de la sim et sont déterministes (RNG global + état sim). Ne jamais leur faire lire un état local.
6. Pathfinding et toute nouvelle logique de sim : déterministes (tri stable, tie-break par uid/compteur, pas d'itération de `dict` non ordonné pour des décisions).

## Joueurs et équipes

- 2 à 8 joueurs (`MAX_PLAYERS`), slots dans `config["players"]` : `{ai: bool, team: 1..8}`. En LAN les slots 0/1 sont humains ; en solo seul le slot 0.
- `pid` = index du slot (= index dans `Game.players`). Zombies : `pid` 8 (`ZOMBIE_PID`), équipe 99, joueur ajouté en fin de liste — utiliser `Game.combatants` pour les joueurs réguliers, jamais `players[:2]`.
- Alliances : `Player.allied(other)` (même `team`). Ciblage, aggro, portes, splash et brouillard sont par équipe. La victoire = dernière équipe avec au moins un bâtiment (`check_victory`, `Game.winner` est un **numéro d'équipe**).
- Taille de map contrainte : petite ≤ 2 joueurs, moyenne ≤ 4, grande ≤ 8 (`MAP_SIZES[clé][3]`, auto-ajusté dans `game_options`).

## Conventions

- Code et textes de jeu en **français** (l'utilisateur écrit en français, style décontracté).
- Sections séparées par des bannières `# ---- nom` ; constantes de données en dicts dans `data.py`.
- Sprites : jamais de fichiers image, tout est peint dans `art.py` et mis en cache dans `ART`.
- Un compteur de version doit etre tenu a jour et incrémenté a chaque modification, il doit etre visible dans le jeux au démarage.
- Tu dois gerer le repo git a chaque modification.

## Pièges connus

- `SCREEN_W/H` fixes (1280×720) ; plein écran via `pygame.SCALED` (F11), ne pas changer la résolution logique.
- Les dimensions de carte sont des **attributs de Game** (`self.map_w/map_h/world_w/world_h`), calculés depuis `config["map"]` — plus de globales à muter.
- `MAP_SIZES` : tuples `(nom, largeur, hauteur, joueurs_max)` — 4 éléments.
- `Building._next_id` / `Unit._next_id` réinitialisés dans `Game.__init__` (nécessaire au lockstep).
- Les groupes de contrôle (1..5) contiennent unités **et** bâtiments ; double-appui = centrer la caméra (local, `time.monotonic`).
- La file de chantiers d'un ouvrier (`Unit.build_queue`) est vidée par tout ordre explicite move/attack/harvest.
