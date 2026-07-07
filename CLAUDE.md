# CRISTALIS — La Guerre des Cristaux

RTS 2D en pygame, en français. Récolte de cristaux, construction de base, armée, destruction des bases ennemies. Solo contre IA (2 à 8 joueurs, équipes) ou multijoueur LAN.

## Lancement et tests

- Python du projet : sous Windows, `python` global (3.13, pygame 2.6.1, numpy) ; sous Linux, `venv/bin/python` si le venv existe (`./run.sh`).
- Jouer : `python cristalis.py`
- Test auto sans fenêtre (IA vs IA) : `python cristalis.py --autotest`
- Smoke test rendu headless (240 frames) : variable d'env `CRISTALIS_SMOKE=1` puis `python cristalis.py`
- Suite de tests headless **versionnée dans le repo** : `python test_features.py` (sanitize_config, mode Survie, menu pause/Échap, déterminisme `state_hash`). À lancer après toute modification, et à compléter pour toute nouvelle fonctionnalité.
- Test lockstep 2 processus : script `mp_sim.py host|join` à recréer dans le scratchpad au besoin (les `state_hash` host/join doivent être égaux entre eux ; ils varient d'une exécution à l'autre, artefact du script).

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
- Le Readme.md doit toujour etre mis a jour, c'est la porte d'entré lorsque l'on regarde le projet sur github.

## Pièges connus

- `SCREEN_W/H` fixes (1280×720) ; plein écran via `pygame.SCALED` (F11), ne pas changer la résolution logique.
- Les dimensions de carte sont des **attributs de Game** (`self.map_w/map_h/world_w/world_h`), calculés depuis `config["map"]` — plus de globales à muter.
- `MAP_SIZES` : tuples `(nom, largeur, hauteur, joueurs_max)` — 4 éléments.
- `Building._next_id` / `Unit._next_id` réinitialisés dans `Game.__init__` (nécessaire au lockstep).
- Les groupes de contrôle (1..5) contiennent unités **et** bâtiments ; double-appui = centrer la caméra (local, `time.monotonic`).
- La file de chantiers d'un ouvrier (`Unit.build_queue`) est vidée par tout ordre explicite move/attack/harvest.
- Le mode Survie (`difficulty == "survie"`) est **solo uniquement** : il consomme le RNG global (`update_survival_zombies`) et lit `self.me` dans `check_victory` — interdit de le brancher en LAN sans le rendre déterministe.
- `survival_scores.json` est un fichier de données utilisateur : gitignoré, ne jamais le committer.

## Malfaçons LLM à éviter (leçons de la revue v0.5→v0.13)

Erreurs réellement produites par un LLM sur ce projet, corrigées en v0.14. À relire avant toute modification :

1. **Jamais de « test » purement statique.** Neuf versions ont été livrées avec pour seul test « vérification via get_errors ». Un jeu se teste en le faisant tourner : `python cristalis.py --autotest` + `python test_features.py` au minimum, et un test headless dédié pour chaque nouvelle fonctionnalité.
2. **UI et code doivent rester synchrones.** Le handler `Échap → retour menu` a été supprimé alors que l'écran de fin affichait toujours « Échap : retour au menu ». Chaque texte d'aide/hint affiché doit correspondre à un handler réellement câblé — vérifier les deux côtés à chaque changement de raccourci.
3. **Pas de sortie de secours qui dépend du lockstep.** « P puis QUITTER » pour quitter après une connexion perdue ne pouvait pas marcher : la pause passe par `issue()` et la sim est gelée quand le pair est mort. Toute action de sortie/UI d'urgence doit être locale (`request_return_menu`), jamais une commande lockstep.
4. **Relire la demande d'origine.** Le prompt demandait « Échap → fenêtre de confirmation de sortie » ; le LLM l'a mise sur `P` et laissé Échap sur la désélection. Implémenter ce qui est demandé, ou documenter explicitement l'écart.
5. **Pas de changement d'équilibrage silencieux.** Toutes les tailles de cartes ont été doublées sans que ce soit demandé ni documenté dans le DEVLOG. Tout changement de gameplay/équilibrage doit être demandé, ou a minima signalé et justifié.
6. **Penser aux ordres de grandeur.** La carte « géante » 512×256 cases créait une surface de fond de 16384×8192 px ≈ **537 Mo**. Avant d'ajouter une taille/quantité, calculer la mémoire et le coût CPU (fond, brouillard, A*).
7. **Langue française partout**, y compris les messages de jeu (« Zombies are coming! » a fusé jusque dans le README).
8. **Une seule source de vérité pour la géométrie UI.** Les rects du menu pause étaient définis en double (game.py et render.py) ; la moindre retouche les aurait désalignés (hitbox ≠ dessin). Centraliser (cf. `pause_menu_rects`).
9. **Ne pas muter la sim depuis l'UI.** Le bouton QUITTER faisait `self.paused = False` en direct, hors `issue()` — violation de l'invariant lockstep n°1, même si bénigne ici.
10. **Pas de code mort « défensif »** (ex. `if self.local_pid >= len(self.combatants)` inatteignable) : ça masque les vrais bugs au lieu de les révéler.
11. **Hygiène de repo** : fichiers générés gitignorés dès leur création, newline final dans chaque fichier, numéro de version cohérent (0.4 → 0.13 en une seule livraison n'a pas de sens).
