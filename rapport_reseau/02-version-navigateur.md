# 02 — Faire tourner CRISTALIS dans un navigateur

Rapport détaillé, rédigé pour servir de **brief à un autre LLM** qui ferait le
portage. Les sections « ⚠ à vérifier » signalent les points dont l'API exacte
doit être confirmée dans la doc au moment de l'implémentation.

## 1. La filière technique : pygbag (pygame → WebAssembly)

Il n'existe qu'une voie sérieuse pour exécuter ce code **tel quel** dans un
navigateur : **pygbag** (https://pygame-web.github.io). C'est un packager qui
embarque un CPython compilé en WebAssembly (via Emscripten) + SDL2, et sert le
jeu comme une page web. Le code reste du Python — pas de réécriture en JS.

Alternatives écartées :
- **Pyodide** : excellent CPython-wasm généraliste, mais pas de SDL2/pygame —
  il faudrait réécrire tout le rendu sur canvas. Non.
- **Réécriture JS/TS (Phaser…)** : réécriture complète de 6000+ lignes, perte
  du déterminisme commun avec le natif. Non.
- **Streaming (le jeu tourne sur serveur, le navigateur reçoit de la vidéo)** :
  infra hors de proportion. Non.

Prérequis pygbag : le projet doit tourner avec **pygame-ce** (fork communautaire,
API identique pour tout ce que CRISTALIS utilise). À tester en natif d'abord :
`pip install pygame-ce` et lancer la suite de tests.

## 2. Ce qui doit changer dans CRISTALIS (le cœur du brief)

### 2.1 Boucle de jeu asynchrone — le gros morceau

Dans le navigateur, il n'y a **pas de boucle bloquante** : le code doit rendre
la main au navigateur à chaque frame. Pygbag impose :

```python
import asyncio

async def main():
    ...
    while True:
        ...une frame...
        await asyncio.sleep(0)   # OBLIGATOIRE : rend la main au navigateur

asyncio.run(main())
```

Conséquence pour CRISTALIS : **toute boucle `while` qui contient
`clock.tick()` doit devenir `async` et se terminer par `await asyncio.sleep(0)`**.
Recensement (à jour de la v0.15) :

- `cristalis.py` : `run_solo`, `run_multiplayer`, `run_autotest`, `main` ;
- `menus.py` : chaque écran a sa boucle (`menu`, `pick_difficulty`,
  `game_options`, `survival_options`, `lan_host`, `lan_join`,
  `wait_handshake`) — toutes à passer en `async def` + `await` en cascade.

C'est mécanique mais envahissant (une dizaine de fonctions). La sim
(`game.py`, `entities.py`, `ia.py`) et le rendu (`render.py`, `art.py`)
ne changent **pas** : ils sont appelés depuis la boucle, ils ne bloquent pas.
Piège : ne jamais insérer d'`await` **entre** deux mutations de la sim — tout
le tick doit rester synchrone (invariant lockstep).

Astuce de compatibilité : garder le natif fonctionnel avec le même code —
`asyncio.run(main())` marche aussi en natif, seul `clock.tick(60)` reste utile
nativement (dans le navigateur c'est le `requestAnimationFrame` qui cadence ;
laisser les deux est acceptable).

### 2.2 Réseau : les sockets bruts n'existent pas dans le navigateur

`netcode.py` est inutilisable tel quel en wasm : pas de `socket` TCP/UDP, pas
de `threading` fiable (le `Thread` de `Peer._recv_loop` ne tournera pas), pas
de broadcast de découverte. Le navigateur n'offre que **WebSocket** (TCP-like,
via un serveur) et WebRTC (P2P, complexe).

Architecture recommandée — **un relais WebSocket** (le même que l'option C du
rapport 01) :

1. Écrire `netcode_ws.py` avec une classe `PeerWS` qui expose **exactement la
   même interface que `Peer`** : `send(obj)`, `poll() -> list`, `alive`,
   `close()`. Tout `run_multiplayer` fonctionne alors sans modification.
2. Côté navigateur : ouvrir la WebSocket via l'API JS exposée par pygbag.
   ⚠ à vérifier : le module de pont (`platform.window` / `javascript` /
   `aio.net` selon la version de pygbag) — la doc pygame-web a des exemples
   multijoueur WebSocket à jour ; c'est LE point à confirmer en premier.
3. Côté natif : la même `PeerWS` avec la lib `websockets` (asyncio) — ainsi
   natif et web utilisent le même relais et le même protocole (les mêmes
   lignes JSON qu'aujourd'hui, une ligne = un message WebSocket texte).
4. Serveur relais : ~150 lignes Python/asyncio (`websockets`), rooms par code
   de partie. Aucune logique de jeu.

La découverte UDP (`Discovery`/`HostListener`) reste réservée au LAN natif.

### 2.3 Autres adaptations obligatoires

- **Fichiers** : `survival_scores.json` — en wasm le système de fichiers est
  virtuel et volatil. Pygbag monte un stockage persistant navigateur
  (IndexedDB). ⚠ à vérifier : le chemin monté persistant et s'il faut un
  « sync » explicite ; sinon, accepter la perte des scores web au premier jet.
- **Son** : `pygame.mixer.pre_init(...)` + synthèse numpy. Deux pièges :
  (a) numpy en wasm — pygbag sait charger certains paquets purs/portés,
  ⚠ à vérifier si numpy en fait partie dans la version courante ; le jeu
  a déjà un repli « sans numpy → pas de sons », le garder actif au premier
  jet ; (b) les navigateurs bloquent l'audio avant le premier clic — pygbag
  gère un écran « cliquer pour démarrer », ne pas s'en étonner.
- **Plein écran / résolution** : `pygame.SCALED` + F11 — dans le navigateur
  c'est le canvas qui se met à l'échelle. Garder la résolution logique fixe
  1280×720 (déjà le cas), ne rien changer.
- **`time.monotonic()`** (double-clic groupes de contrôle) : fonctionne en
  wasm, rien à faire.
- **Entrées** : clavier/souris OK. Attention au clic droit : il faut inhiber
  le menu contextuel du navigateur — pygbag le fait sur le canvas (⚠ vérifier).
- **Structure de projet imposée** : pygbag veut un `main.py` à la racine du
  dossier packagé. Renommer/wrapper `cristalis.py` en `main.py` (ou un
  `main.py` qui importe et lance `cristalis.main()`).

### 2.4 Performances : le vrai risque du portage

CPython-wasm est **2 à 5× plus lent** que CPython natif, sur un seul thread.
Points chauds connus du projet (mesurés en natif, v0.15) :

- La sim à 20 Hz (unités, A* plafonné à 9000 expansions, IA) : OK sur cartes
  petites/moyennes, à surveiller au-delà de ~150 unités.
- Le rendu : ~4 ms/frame natif → 10-20 ms wasm : jouable à 60 fps sur carte
  moyenne, probablement 30 fps sur grande.
- **Recommandation ferme : limiter la build web aux cartes petite/moyenne au
  premier jet** (la géante 512×256 est hors budget wasm), et mesurer avant
  d'ouvrir plus. Prévoir un `data.IS_WEB` (détectable via
  `sys.platform == "emscripten"`) pour ajuster `MAP_SIZES` et les effets.

### 2.5 Déterminisme croisé natif ↔ web

Le lockstep suppose des sims bit-identiques. Web↔web : même wasm des deux
côtés, aucun risque. **Natif↔web : à valider avant de l'autoriser** — flottants
IEEE754 et `random` de CPython sont en principe identiques, mais versions de
Python différentes (le CPython de pygbag vs le 3.13 local) peuvent diverger
subtilement (ordre de dict garanti, mais détails de `random`/maths possibles).
Test : reproduire `mp_sim.py` avec un pair natif et un pair web et comparer
les `state_hash` sur 10 min. En attendant : matchmaking séparé web/natif.

## 3. Infrastructure à mettre en place

| Brique | Rôle | Options | Coût |
|---|---|---|---|
| Hébergement statique | Servir la page + le wasm (~20-40 Mo) | **itch.io** (pensé pour pygbag, page jeu clé en main), GitHub Pages, ou le même VPS derrière nginx/Caddy | 0 € |
| Relais WebSocket | Multijoueur (rooms par code) | VPS Hetzner CX22 (~4 €/mois) avec TLS (`wss://` **obligatoire** si la page est en https) via Caddy ; alternatives : fly.io petit tier | ~4 €/mois |
| Nom de domaine | wss:// propre + page | optionnel mais pratique | ~10 €/an |

Notes :
- ⚠ Si pygbag exige les en-têtes COOP/COEP (SharedArrayBuffer) selon la
  version : itch.io a une case à cocher pour ça ; GitHub Pages ne permet pas
  d'en-têtes custom → itch.io ou VPS de préférence.
- Un **VPS unique** peut tout porter : page statique + relais wss. C'est le
  choix le plus simple à administrer.
- Pas besoin de « serveur de jeu » : le lockstep fait tourner la sim chez les
  joueurs, le serveur ne fait que relayer quelques Ko/s.

## 4. Plan de travail proposé (pour l'LLM exécutant)

1. **Spike (½ j)** : `pip install pygame-ce pygbag`, wrapper `main.py`,
   passer `run_solo` + `menu` en async, `pygbag .` → jouer en solo local dans
   le navigateur. Aucun réseau. Critère : 60 fps carte petite.
2. **Async complet (½ j)** : tous les écrans/boucles, tests natifs verts
   (`test_features.py`, autotest, smoke — ils doivent continuer à passer).
3. **Relais + PeerWS (1 j)** : serveur `websockets` avec rooms, `PeerWS`
   natif↔natif d'abord (testable sans navigateur, adapter `mp_sim.py`),
   puis web↔web.
4. **Finitions web (½ j)** : scores persistants, écran tactile non géré →
   afficher « souris requise », `IS_WEB` limitant les cartes.
5. **Publication** : build pygbag sur itch.io + relais sur VPS.
   Vérifier `state_hash` web↔web sur une partie complète.

Règles du dépôt à respecter (CLAUDE.md) : tout en français, DEVLOG à chaque
étape, compteur de version, ne jamais brancher le mode Survie en LAN tel quel,
et tester en exécutant (autotest + test_features), pas seulement statiquement.
