# DEVLOG — CRISTALIS

Journal de développement. Une entrée par session de travail, la plus récente en haut.
Format : date — résumé, détails par fonctionnalité, tests effectués, dettes/TODO.

## 2026-07-09 — Refonte IA par difficulté (éco/build/defense/attaque) — v0.16

Refonte du contrôleur `AIController` pour coller aux rôles demandés par mode.
Le comportement n'est plus seulement un changement de chiffres : chaque
difficulté possède maintenant une doctrine propre sur l'économie, la
construction, la composition d'armée, la défense et les offensives.

### Changements de gameplay IA
- `game.py` : passage de la clé de difficulté (`self.diff_key`) au
  contrôleur IA pour activer des branches de logique spécifiques.
- `data.py` : ajustement des paramètres `DIFFICULTES` (income, workers,
  wave, tempo, pauses de production) et incrément de version `0.15 -> 0.16`.
- `ia.py` :
  - cadence de réflexion différente selon la difficulté ;
  - plans de construction distincts :
    - Facile limité à obélisque/caserne/archerie ;
    - Normal tech complète équilibrée ;
    - Difficile expansion QG périphérique + tours + murailles ;
  - assignation de bâtisseurs renforcée sur les chantiers critiques ;
  - files de production et compositions d'armée différenciées ;
  - garnison permanente au village (taille/type selon difficulté) ;
  - réaction défensive en cas de menace locale (retour défendre la base) ;
  - ciblage tactique des unités dangereuses (Normal/Difficile) ;
  - repli stratégique à perte d'effectif, puis relance d'offensive par vagues.
- `README.md` : section IA détaillée par mode (Facile/Normal/Difficile)
  + version affichée mise à jour.

### Tests
- `python test_features.py` : OK (suite complète verte).
- `python cristalis.py --autotest` : lancé, progression observée (`t=60s ...`),
  pas d'erreur Python signalée.
- `CRISTALIS_SMOKE=1 python cristalis.py` : lancé, progression observée
  (`t=180s ...`), pas d'erreur Python signalée.

### Notes
- La refonte reste déterministe LAN : RNG global + état simulation uniquement.

## 2026-07-07 — Grandes cartes rétablies, fond de carte chunké — v0.15

Sur demande de Bastien, retour aux tailles de cartes de la livraison v0.5→v0.13
(petite 96×68, moyenne 128×88, grande 192×128, géante 512×256), qui avaient été
ramenées aux valeurs d'origine en v0.14 à cause de leur coût mémoire. Cette
fois la cause est corrigée au lieu de réduire les cartes.

### Pourquoi c'était lent / lourd
- `art.make_terrain` peignait **toute la carte dans une seule surface** au
  lancement : géante 512×256 cases = 16384×8192 px ≈ **537 Mo** de RAM et
  3,2 s de génération (mesuré ; bien pire sur un portable modeste, où ça part
  en swap — cause probable de la lenteur constatée chez l'ami du projet).
- Le voile de brouillard de la minimap était reconstruit case par case en
  Python à chaque mise à jour du brouillard (toutes les 0,15 s) : **27,8 ms**
  par reconstruction sur la géante.
- `update_fog` fusionnait exploré/visible par une boucle Python pleine carte
  (2,8 ms sur la géante, toutes les 0,15 s).

### Corrections
- **`art.Terrain`** remplace `make_terrain` : fond découpé en chunks de
  256×256 px générés à la demande (graine spatiale déterministe par chunk),
  cache LRU borné à 160 chunks ≈ **42 Mo maximum quelle que soit la carte**.
  Préchargement amorti (un anneau d'avance, 2 chunks max par frame) pour
  lisser le défilement. Places et chemins (`bake_plaza`/`bake_path`) cuits en
  overlays appliqués au rendu des chunks. Rendu local uniquement (RNG dédiés),
  aucun impact lockstep.
- **Minimap** : le fond réduit est échantillonné directement depuis le bruit
  (`Terrain.minimap`), plus de `smoothscale` d'une surface plein monde ; le
  voile de brouillard est construit par opérations sur octets
  (`int.from_bytes` + `translate` + `frombuffer`) : 27,8 ms → **1,1 ms**.
- **`update_fog`** : fusion exploré |= visible par OU sur entiers
  (2,8 ms → ~0 ms).
- Chunks convertis au format écran (`convert()`), blits plus rapides.

### Mesures (machine de dev, carte géante 512×256, 4 joueurs)
- init : 3,18 s → **0,07 s** ; fond : 537 Mo → **≤ 42 Mo**.
- draw en défilement continu : médiane 4,0 ms, p95 8,6 ms (le max ~95 ms est
  la toute première frame : vue initiale + minimap, une fois par partie).
- Téléportation minimap (vue entière à régénérer) : 47,8 ms, une frame.

### Tests
- `python test_features.py` : 9/9 OK (2 nouveaux : `test_terrain_chunks`
  — déterminisme, éviction LRU, overlays, bords de carte, minimap — et
  `test_fog_ops` — équivalence des fusions d'octets avec les anciennes
  boucles).
- `python cristalis.py --autotest` : OK (victoire Ordre d'Azur à t=500 s sur
  la moyenne 128×88).
- Smoke test rendu `CRISTALIS_SMOKE=1` : exit 0.

### Notes / TODO
- Le rendu du fond n'est plus identique au pixel près à l'ancien (les touffes
  d'herbe et taches sont semées par chunk et non plus globalement) : même
  style visuel, purement cosmétique et local.
- La lenteur signalée « en lançant via VS Code » : le terminal intégré est
  neutre, mais **lancer avec F5 (débogueur) ralentit fortement Python** —
  lancer avec `python cristalis.py` sans débogueur.
- TODO inchangés : horde de zombies O(n²), condition de défaite Survie
  limitée au QG.

## 2026-07-07 — Revue et correction des livraisons v0.5→v0.13 — v0.14

Revue critique des modifications apportées par un LLM tiers (mode Survie,
menu pause, carte géante). Fonctionnalités conservées, malfaçons corrigées,
tests ajoutés. Les leçons sont consignées dans CLAUDE.md (« Malfaçons LLM à
éviter »).

### Bugs corrigés
- **Écran de fin** : le hint affichait « Échap : retour au menu » mais le
  handler avait été supprimé — Échap ne faisait plus rien. Rétabli via
  `on_key` (`request_return_menu`).
- **LAN, connexion perdue** : « P puis QUITTER » ne pouvait pas fonctionner,
  la pause étant une commande lockstep et la sim gelée sans le pair. Échap
  ramène désormais directement au menu (action locale) quand le pair est
  déconnecté ou la partie finie ; hint corrigé.
- **Échap conforme à la demande d'origine** : annule un placement, sinon
  désélectionne, sinon ouvre le menu pause (confirmation de sortie avec
  REPRENDRE/QUITTER). Échap dans le menu pause = reprendre.
- **Carte Géante 512×256** : surface de fond de 537 Mo. Ramenée à 160×104
  (~68 Mo). Les tailles petite/moyenne/grande, doublées silencieusement sans
  demande ni documentation, sont revenues aux valeurs d'origine (48×34,
  64×44, 96×64).
- **« Zombies are coming! »** → « Les zombies arrivent ! » (jeu 100 % FR),
  aussi dans le README.

### Nettoyages
- `pause_menu_rects()` renvoie aussi le panneau : une seule source de vérité
  pour la géométrie du menu pause (avant : constantes dupliquées dans
  game.py et render.py).
- QUITTER ne mute plus `self.paused` en direct (violation de l'invariant
  lockstep n°1, inutile puisqu'on quitte la boucle).
- `update_survival_zombies` : liste des zombies calculée une fois,
  `spawn_border_zombie` renvoie l'unité créée ; docstring sur la restriction
  solo (RNG global consommé).
- `save_survival_score` : logique « nouveau record » simplifiée
  (`score > ancien best`).
- Suppression du code mort (`local_pid >= len(combatants)`, early-return
  `request_return_menu` dans `update`), du doublon de config SMOKE et des
  deux sliders copiés-collés dans `survival_options`.
- `survival_scores.json` gitignoré ; newline final rétabli dans render.py et
  prompt.txt ; `main()` dédoublonné.

### Tests
- Nouveau `test_features.py` **versionné dans le repo** : sanitize_config,
  tailles de cartes bornées en mémoire, Survie (préparation, invasion,
  remplacement des morts, défaite, sauvegarde/record), Échap/menu
  pause/QUITTER/écran de fin, déterminisme (`state_hash` de deux sims à seed
  identique).
- Exécutés et verts : `python test_features.py` (7/7),
  `python cristalis.py --autotest` (victoire équipe 2 à t=521s),
  smoke test rendu (`CRISTALIS_SMOKE=1`, 240 frames).

### Dettes/TODO
- Le regroupement en hordes est O(n²) par frame ; acceptable jusqu'à ~200
  zombies, à optimiser (grille spatiale) si on augmente la pression.
- En Survie, la défaite ne regarde que le QG ; les autres bâtiments ne
  comptent pas (comportement documenté, à revoir si souhaité).

## 2026-07-06 — Échap : désélection + annulation placement — v0.13

### Changement demandé
- La touche `Échap` doit aussi annuler un placement en cours.

### Implémentation
- `game.py`
  - `on_key` : `Échap` exécute `self.selection.clear()` et `self.placing = None`.
  - Aucun autre effet ajouté : pause/menu inchangés.

### Version et docs
- Version incrémentée à `0.13` (`data.py`).
- README ajusté : `Échap` désélectionne et annule un placement.

### Tests effectués
- Vérification statique ciblée sur `game.py` via `get_errors`.

## 2026-07-06 — Échap limité à la désélection — v0.12

### Changement demandé
- Conserver uniquement l'action de désélection sur la touche `Échap`.

### Implémentation
- `game.py`
  - `on_key` : `Échap` exécute uniquement `self.selection.clear()`.
  - Suppression des effets annexes précédents (annulation placement/attaque-move,
    retour menu de fin de partie via `Échap`).

### Version et docs
- Version incrémentée à `0.12` (`data.py`).
- README mis à jour (table des commandes : `Échap` = désélectionner tout).

### Tests effectués
- Vérification statique ciblée sur `game.py` via `get_errors`.

## 2026-07-06 — Sortie de partie via menu pause (bouton QUITTER) — v0.11

### Changement demandé
- Suppression de la sortie de partie via `Échap` pendant une partie en cours.
- Ajout d'un vrai menu de pause avec deux boutons : **REPRENDRE** et **QUITTER**.

### Implémentation
- `game.py`
  - La gestion d'événements en pause passe par `handle_pause_menu_event`.
  - Nouveau calcul des zones cliquables via `pause_menu_rects`.
  - Clic sur **REPRENDRE** (ou touche `P`) : reprise de la partie.
  - Clic sur **QUITTER** : retour au menu principal (`request_return_menu = True`).
  - `Échap` ne déclenche plus de demande de sortie en partie active.
- `render.py`
  - Remplacement de l'ancien popup de confirmation par `draw_pause_menu`.
  - Overlay pause avec boutons **REPRENDRE** / **QUITTER** et hover visuel.
- `cristalis.py`
  - Message LAN "connexion perdue" aligné avec le nouveau flux :
    "P puis QUITTER : retour au menu".

### Version et docs
- Version incrémentée à `0.11` (`data.py`).
- README synchronisé avec le nouveau comportement de sortie en partie.

### Tests effectués
- Vérification statique sur les fichiers modifiés via `get_errors`.

## 2026-07-05 — Correctif crash popup Échap (AttributeError) — v0.10

### Bug corrigé
- Crash au lancement d'une partie dès affichage de la confirmation Échap :
  `AttributeError: 'Game' object has no attribute 'draw_quit_confirm'`.
- Cause : `draw_quit_confirm` était accidentellement imbriquée dans `draw_end`
  au lieu d'être une méthode de classe `RenderMixin`.

### Correctif appliqué
- Méthode `draw_quit_confirm` remise au bon niveau d'indentation (méthode de
  classe dans `render.py`).
- Texte d'aide du popup normalisé en ASCII (`Entree` / `Echap`) pour éviter les
  caractères corrompus selon l'encodage terminal.

### Version et docs
- Version incrémentée à `0.10` (`data.py`).
- README synchronisé avec la version `0.10`.

### Tests effectués
- Vérification statique `get_errors` sur `render.py`, `cristalis.py`, `game.py` :
  aucune erreur sur le correctif (hors avertissement numpy déjà existant).

## 2026-07-05 — Confirmation de sortie sur Échap en partie — v0.9

### Fenêtre de confirmation
- En cours de partie, `Échap` n'efface plus simplement la sélection : une
  fenêtre de confirmation s'affiche désormais.
- La fenêtre propose :
  - **Oui** (clic, `Entrée` ou `Y`) : quitter la partie et revenir au menu,
  - **Non** (clic, `Échap` ou `N`) : fermer la fenêtre et reprendre la partie.

### Intégration gameplay
- Ajout d'un état modal dans `Game` (`confirm_quit`) qui fige la simulation tant
  que la confirmation est ouverte.
- Ajout d'un signal `request_return_menu` consommé par les boucles `run_solo` et
  `run_multiplayer` pour revenir à l'accueil.
- En LAN, la sortie confirmée envoie un `bye` au pair avant retour menu.

### Rendu/UI
- Ajout d'un overlay visuel de confirmation dans `RenderMixin` avec deux boutons
  stylés et rappel des raccourcis clavier.
- Harmonisation du texte de fin de partie solo : `Échap` indique désormais le
  retour au menu.

### Version et docs
- Version incrémentée à `0.9` (`data.py`).
- README mis à jour avec la règle de confirmation sur `Échap`.

### Tests effectués
- Vérification statique après patch via `get_errors` (voir entrée de session).

## 2026-07-05 — Menu de configuration Survie zombie + timings paramétrables — v0.8

### Menu Survie dédié
- Ajout d'un écran `survival_options` dans `menus.py`, appelé juste après le
  choix de difficulté quand le joueur choisit **Survie zombie**.
- Paramètres configurables :
  - carte : petite / moyenne / grande / géante,
  - intervalle d'apparition d'un nouveau zombie : 5s à 120s,
  - délai avant le début de l'invasion : 0 à 10 minutes.

### Intégration simulation
- La config de partie inclut maintenant :
  - `zombie_spawn_interval` (par défaut 60, borné 5..120),
  - `zombie_invasion_delay` (par défaut 120, borné 0..600).
- En mode Survie, `Game` lit ces valeurs pour piloter :
  - le décompte de préparation,
  - la cadence réelle des vagues,
  - le démarrage immédiat de l'invasion si délai = 0.
- La carte n'est plus forcée à "moyenne" en Survie : la valeur choisie dans le
  menu est utilisée.

### Version et docs
- Version incrémentée à `0.8` (`data.py`).
- README mis à jour pour documenter le nouveau menu de configuration Survie.

### Tests effectués
- Vérification statique après patch via `get_errors` (voir entrée de session).

## 2026-07-05 — Nouveau mode "Survie zombie" + score persistant — v0.7

### Condition de défaite Survie (QG)
- En mode Survie, le joueur perd dès qu'il ne possède plus de Quartier Général,
  même s'il reste d'autres bâtiments.

### Brouillard en fin de partie
- Désactivation automatique du brouillard de guerre quand la partie est terminée
  afin de voir toute la carte et toutes les entités.

### Ajustement spawn Survie (QG vs cristaux)
- Décalage du QG de départ en mode Survie (`game.py`, `gen_map`) pour éviter
  qu'il apparaisse dans la zone de cristaux centrale au lancement.

### Ajustement cadence Survie (zombies)
- Mode Survie : aucun zombie au démarrage.
- Cadence d'invasion fixée à +1 zombie toutes les 20 secondes (au lieu de 10).

### Préparation avant invasion (nouvelle règle)
- Ajout d'un délai de préparation de 2 minutes en mode Survie.
- Affichage d'un décompte "Préparation mm:ss" dans la topbar.
- À 0, message exact "Zombies are coming!", démarrage du chrono de survie et
  début des arrivées de zombies.
- Le score enregistré de Survie repose désormais sur le chrono de survie
  (`survival_time`) et non sur le temps global de simulation.

### Nouveau mode de difficulté
- Ajout de `survie` dans `DIFFICULTES` (libellé **Survie zombie**), visible dans
  le menu de sélection des difficultés.
- En solo, ce mode force une config dédiée : carte **moyenne**, zombies activés,
  une seule faction humaine, vitesse normale.

### Règles du mode Survie
- Spawn du joueur au centre de la carte (QG central).
- Condition de fin spécifique : la partie s'arrête quand le joueur n'a plus de
  bâtiment (pas de condition de victoire classique RTS).
- Invasion continue :
  - +1 zombie cible toutes les 20 secondes (entrée par un bord de map),
  - remplacement immédiat des zombies morts pour maintenir la pression.
- Déplacement zombie : errance aléatoire sur la carte en attaque-move.
- Regroupement/hordes : quand un zombie rencontre un autre zombie proche, il
  reprend sa destination pour se déplacer en groupe.

### Score et HUD
- Score = temps de survie (`self.time`).
- Sauvegarde des sessions dans `survival_scores.json` (top 20), record chargé au
  démarrage et affiché dans la topbar.
- Écran de fin adapté ("FIN DE SURVIE", meilleur temps, indication nouveau record).
- Aide F1 adaptée avec objectif spécifique du mode Survie.

### Documentation et version
- Version incrémentée : `data.VERSION = "0.7"`.
- README mis à jour : section dédiée au mode Survie zombie + version 0.7.

### Tests effectués
- Vérification statique : `get_errors` sur workspace -> aucune erreur.
- Pas de run automatisé relancé dans cette session (autotest/smoke non exécutés).

## 2026-07-02 (5e session) — Mise à jour du README (rattrapage)

- Le README n'avait pas été actualisé lors de la session v0.4 : ajout des deux
  champions d'élite (**Maelan** `N` et **Adryann** `Y`) dans la table des unités,
  avec un paragraphe décrivant la dévoration d'Adryann (+10 % PV max, ni cadavre
  ni tombe, petits cadeaux cosmétiques).
- Mention de la version courante (0.4) en tête du README.
- Formalisation de la règle correspondante dans CLAUDE.md (README toujours à jour).
- Pas de modification de code, pas de test à relancer.

## 2026-07-02 (4e session) — Unités d'élite Maelan et Adryann (caserne) + compteur de version — v0.4

### Deux unités fortes produites à la Caserne (demande utilisateur)
- **Maelan** (petit ninja) : 450 cristaux, 200 PV, 20 ATQ, portée 20, vitesse 100,
  cadence 1,7 coups/s (cooldown 0.6), ravitaillement 3, hotkey [N]. Sprite : tenue
  sombre, katana, écharpe et bandeau couleur d'équipe.
- **Adryann** (bouboule vorace) : 420 cristaux, 200 PV, 20 ATQ, portée 20, vitesse 60,
  cadence 1 coup/s, ravitaillement 3, hotkey [Y]. Sprite : gros ventre qui déborde,
  bouche grande ouverte. Prix « proportionnels au soldat » (75 cristaux) : ~6× le
  coût pour ~2× les PV et 2-3× les dégâts par seconde.
- Mécaniques d'Adryann :
  - **Dévoration** : quand il tue une unité (`Game.kill_unit`, attaquant mêlée),
    il récupère 10 % de ses PV max ; la victime ne laisse ni cadavre ni pierre
    tombale (mangée). Déterministe : uniquement état sim.
  - **Petits cacas** : en marchant, ~1 fois toutes les 2 s (RNG global consommé
    dans la sim, donc identique des deux côtés en LAN), il dépose un
    `art.caca_sprite()` cosmétique dans `game.corpses` (s'estompe en 10 s).
- Caserne : `prod=["soldat", "maelan", "adryann"]` ; IA : prefs caserne
  3× soldat / 1× maelan / 1× adryann. Aide (F1) mise à jour (panneau +28 px).

### Compteur de version (nouvelle règle CLAUDE.md)
- `data.VERSION = "0.4"` : affiché en bas à droite de tous les écrans de menu
  et dans le titre de la fenêtre. À incrémenter à chaque modification.

### Tests
- Script headless (scratchpad `test_new_units.py`) : données, sprites 16 orientations
  × 9 factions, production caserne, dévoration (+20 PV, pas de tombe en mode zombie),
  6 cacas semés en 12 s de marche, déterminisme (2 sims même seed → même `state_hash`).
- `--autotest` OK (victoire Légion Karmin à t=521 s), smoke rendu 240 frames OK.
- Aperçu visuel des sprites générés en PNG (soldat/maelan/adryann/caca).

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
