# DEVLOG — CRISTALIS

Journal de développement. Une entrée par session de travail, la plus récente en haut.
Format : date — résumé, détails par fonctionnalité, tests effectués, dettes/TODO.

## 2026-07-02 (3e session) — Découpage en modules, multi-joueurs 8 max + équipes, vignettes, QoL

### Découpage (plan de la session précédente, exécuté)
- `cristalis.py` (~3200 lignes) éclaté en : `data.py` (constantes, importé en premier
  pour l'env SDL headless), `entities.py`, `ia.py`, `render.py` (RenderMixin, dessin
  pur), `game.py` (Game = sim + commandes + entrées), `menus.py`, `cristalis.py`
  (entrée + boucles, réexports pour les scripts de test).
- Simplifications au passage : MAP_W/WORLD_W ne sont plus des globales mutées mais
  des **attributs de Game** (fin du piège documenté) ; `Game.update` scindé
  (`update_effects`, `check_victory`) ; imports nettoyés.

### Multi-joueurs (max 8) + équipes
- `config["players"]` : liste de slots `{ai, team}` (2 à 8). Écran `game_options`
  refait en deux colonnes : gauche = joueurs (ajout/retrait d'IA, clic sur
  « Équipe N » pour cycler, pastille couleur), droite = vitesse/zombies/carte.
- `Player.team` + `allied()` : ciblage, aggro, splash du mage, portes (ouvertes à
  l'équipe), brouillard (vision d'équipe) et pathfinding (portes alliées passantes)
  sont par équipe. Victoire = dernière équipe avec un bâtiment (`Game.winner` =
  numéro d'équipe) ; message « X est éliminé » par faction.
- 8 couleurs de faction dans `art.PLAYER_COLORS` + zombies déplacés en pid 8
  (`ZOMBIE_PID`), exclus via `Game.combatants`.
- Les IA (slots 2+) tournent aussi en LAN : déterministes, donc lockstep OK
  (validé par mp_sim 2 processus en 2v2 + zombies).
- Cartes : petite ≤ 2 joueurs, moyenne ≤ 4, grande ≤ 8 (auto-ajustement du menu).

### Génération de map selon le nombre de joueurs
- 2 joueurs : coins opposés classiques. 3+ : bases réparties sur une ellipse
  (joueur 0 en bas à gauche), chemin de chaque base vers le centre, un gisement
  de cristaux par base décalé vers le centre + gisements neutres proportionnels.
- Zombies initiaux : seuil de distance aux bases dégressif (600/450/300 px).

### Vignettes de sélection (demande utilisateur)
- Sélection multiple : grille de vignettes (icône + barre de PV) jusqu'à 42
  éléments (14 × 3), unités **et** bâtiments, « +N » au-delà. Clic = isoler,
  Shift+clic = retirer de la sélection.

### QoL (demandes utilisateur)
- File de chantiers : Shift+placements successifs → l'ouvrier enchaîne
  automatiquement les constructions (`Unit.build_queue`, vidée par un ordre
  explicite). HUD : « Chantiers en file : N » sur l'ouvrier.
- Groupes de contrôle : acceptent les bâtiments ; double-appui sur 1..5 (<0,4 s)
  centre la caméra sur le groupe (purement local).

### Tests
- `--autotest` OK (victoire IA à t=339 s), smoke OK.
- `test_features.py` : 28/28 OK — pathfinding (2 cas), zombies (6), équipes/alliés
  (5 dont victoire d'équipe), 8 joueurs FFA sur grande (espacement min 675 px),
  déterminisme des hashes (2 joueurs et 2v2 avec zombies), 3 tailles de carte,
  file de construction (3 chantiers enchaînés), groupes + double-appui caméra,
  clamps de vitesse.
- `mp_sim.py` 2 processus (2 humains + 2 IA en 2v2, zombies, 1400 ticks) :
  hashes identiques à tous les points de comparaison.
- Rendu headless : vignettes (50 unités + bâtiments), partie 4 joueurs, tombes.


## 2026-07-02 — Plein écran, pathfinding A*, options de partie, mode zombie, nerf IA facile

### Plein écran (F11)
- `main()` crée l'écran avec `pygame.SCALED` : la résolution logique reste 1280×720,
  le plein écran ne fait qu'étirer l'image (souris et rendu inchangés).
- `global_key(e)` gère F11 (`pygame.display.toggle_fullscreen()`) dans **tous** les
  écrans (menus, options, LAN, jeu). Mentionné dans l'aide (F1) et le pied du menu.
- SMOKE/AUTOTEST : pas de SCALED (driver dummy).

### Pathfinding (unités bloquées par les bâtiments)
- Problème : `step_toward` allait en ligne droite ; un bâtiment posé sur le trajet
  bloquait l'unité définitivement (poussée dehors par `separate_units` à chaque frame).
- Solution : détection de blocage + A* à la demande.
  - `Unit.update` compare le déplacement réel (après collisions) au déplacement
    voulu (`_intend`) ; si < 35 % pendant 0,45 s → `stuck_t` déclenche un repath
    (cooldown `repath_cd` 1,2 s pour ne pas spammer l'A*).
  - `Game.tile_blocked_map(owner)` : grille des cases couvertes par les bâtiments
    (les portes du propriétaire sont passantes), cache invalidé par `block_version`
    (incrémenté à chaque pose/destruction de bâtiment — `exec_place`, IA, `destroy_building`).
  - `Game.find_path` : A* 8 directions, pas de coupe de coin, tie-break déterministe
    (compteur d'insertion), max 9000 expansions, best-effort si le but est inaccessible
    (renvoie le chemin vers la case atteignable la plus proche). Waypoints = centres
    de cases (simplifiés si alignés) + but exact en dernier.
  - `step_toward(dest, dt, stop, game)` suit le chemin s'il existe ; il est jeté si
    la cible s'éloigne de plus de 1,5 case (poursuite d'unités mobiles en ligne droite).
- Déterministe : ne dépend que de l'état sim, aucun RNG.

### Menu d'options à la création de partie (`game_options`)
- Affiché après le choix de difficulté (solo) et avant l'hébergement (LAN hôte).
- Vitesse : slider ×1 (normal, défaut) à ×300 (ralenti). Solo : `game.update(dt/speed)` ;
  LAN : la durée réelle d'un tick devient `TICK_DT * speed` (la sim reste à TICK_DT).
- Mode zombie : case à cocher.
- Taille de carte : petite 48×34 / moyenne 64×44 / grande 96×64 (`MAP_SIZES`,
  `set_map_size()` appelé par `Game.__init__` ; `gen_map` est devenu paramétrique,
  positions relatives à MAP_W/MAP_H, densité de décor constante).
- LAN : l'hôte envoie `cfg` dans le message `hello` avec la seed ; le client la
  récupère (fallback `DEFAULT_CONFIG` pour compat).

### Mode zombie
- Joueur neutre hostile pid 2 (`ZOMBIE_PID`), couleurs vertes dans `art.PLAYER_COLORS`,
  jamais dans la condition de victoire (qui ne regarde plus que `players[:2]`).
- À chaque mort d'unité (sauf zombie) : pierre tombale (`game.tombstones`,
  sprite `art.tombstone_sprite()`), éclosion en zombie après `TOMB_DELAY` = 20 s
  (lueur verte 3 s avant). Les zombies morts ne se relèvent pas.
- Zombies : type d'unité `zombie` (lent, mêlée, aggro 260 → attaque tout joueur à
  proximité via l'auto-acquisition idle existante). Sprite procédural `_paint_zombie`.
- Au départ : 4 à 12 rôdeurs (selon la surface) dispersés à > 600 px des QG.
- Tombes incluses dans `state_hash`.

### IA facile
- Nettement adoucie : income 0.75→0.55, workers 8→6, wave0 7→5, wave_step 2→1,
  prod_pause 6→9 s. Nouvelles clés : `tempo` (divise l'horloge du plan de
  construction, 1.6 en facile) et `wave_max` (12 en facile, au lieu du cap 24/26).

### Tests effectués
- `venv/bin/python cristalis.py --autotest` : OK, vainqueur joueur 0 à t=773 s.
- `CRISTALIS_SMOKE=1` : OK (240 frames).
- Script `test_features.py` (scratchpad) : 16/16 OK — contournement d'un mur
  pré-existant ET apparu en cours de route, zombies initiaux/tombes/éclosion/
  non-propagation, déterminisme des hashes (2 runs même seed, zombies + petite et
  grande map), génération des 3 tailles de map, clamp vitesse.
- `mp_sim.py host|join` (2 processus, 1400 ticks, zombies + petite map, ordres
  amove injectés) : hashes host/join identiques.
- `pygame.SCALED` + `toggle_fullscreen()` validés sur l'écran réel (1280×720 conservé).

### Découpage proposé (réflexion, à faire dans une prochaine session)
`cristalis.py` ≈ 3000 lignes. Découpage à risque faible, dans cet ordre :
1. `data.py` — constantes pures (UNIT_TYPES, BUILDING_TYPES, UPGRADE_TYPES,
   DIFFICULTES, MAP_SIZES, DEFAULT_CONFIG, couleurs C_*, hotkeys). Zéro dépendance.
2. `entities.py` — Player, Doodad, Crystal, Building, Unit, Projectile (dépendent de
   data + art). Attention : TILE/MAP_W sont des globales partagées → les mettre dans
   `data.py` avec `set_map_size` et importer le **module** (`data.MAP_W`), pas les noms.
3. `ai.py` — AIController (dépend d'entities).
4. `menus.py` — MenuUI, menu, pick_difficulty, game_options, lan_host/join, show_net_error.
5. `game.py` — la classe Game, à terme scindée en mixins/fichiers : sim (update,
   commandes, pathfinding, requêtes) vs présentation (draw_*, HUD, minimap, brouillard,
   entrées). La frontière sim/rendu est déjà propre grâce au lockstep — c'est la coupe
   la plus rentable pour la lisibilité et la sécurité des invariants.
6. `cristalis.py` ne garde que les boucles (run_solo, run_multiplayer, run_autotest, main).
Règle de migration : un module à la fois, `--autotest` + smoke + mp_sim verts entre
chaque étape. Initialiser un dépôt git avant le refactor (aucun suivi de version
actuellement !) pour pouvoir bisecter une désync.

## Historique antérieur

- 2026-07-02 (session précédente) : ajout du multijoueur LAN en lockstep déterministe
  (netcode.py, `Game.issue`/`apply_command`, `state_hash`, brouillard de guerre local).
