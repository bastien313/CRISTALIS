# 03 — Navigateur ou natif ? Tour d'horizon

La question de fond : **accessibilité maximale** (une URL et on joue) contre
**maîtrise et performances** (un exécutable par plateforme). Panorama honnête
des deux voies pour CRISTALIS, puis recommandation.

## 1. La voie navigateur (pygbag / WebAssembly)

### Avantages
- **Friction zéro** : un lien à partager, pas d'installation, pas de version
  de Python à gérer, pas d'antivirus qui hurle. C'est LE moyen de faire
  essayer le jeu à quelqu'un en 30 secondes — et pour un jeu multijoueur,
  chaque étape d'installation évitée multiplie les joueurs réels.
- **Multiplateforme gratuit** : Windows, macOS (Intel et ARM), Linux,
  Chromebooks… tout ce qui a un navigateur moderne. Le problème « ARM / mac /
  distro » disparaît entièrement.
- **Mises à jour instantanées** : on republie, tout le monde a la dernière
  version — précieux en lockstep, où deux versions différentes désynchronisent.
- **Même base de code** : pygbag exécute le Python existant ; la sim, l'IA,
  l'art procédural restent identiques (contrairement à une réécriture JS).

### Inconvénients
- **Performances ×2-5 plus lentes** (CPython-wasm, monothread). Cartes
  petites/moyennes OK, la géante 512×256 hors budget. Sur le portable lent
  de ton ami, la version web serait *plus* lente que le natif, pas moins.
- **Chantier async** : toutes les boucles de jeu/menus à passer en `async`
  (~10 fonctions, mécanique mais envahissant — détail au rapport 02).
- **Réseau contraint** : pas de sockets → WebSocket + serveur relais
  obligatoire (~4 €/mois), pas de LAN-découverte. Le multijoueur web ne peut
  pas exister sans cette infra.
- **Environnement capricieux** : audio bloqué avant un clic, stockage
  navigateur pour les scores, poids du bundle (~20-40 Mo à télécharger),
  débogage plus pénible qu'en natif.
- **Public tactile hors de portée** : un RTS à la souris ne se joue pas sur
  téléphone — le navigateur n'apporte pas les joueurs mobiles pour autant.

## 2. La voie native

### Où on en est
Aujourd'hui la distribution c'est « installe Python 3.13, `pip install
pygame`, clone le repo » : réservé aux développeurs. Pour élargir :

### Options de distribution native
| Option | Effort | Résultat |
|---|---|---|
| **PyInstaller / Nuitka** | faible/moyen | un exécutable par OS **et par architecture** (win x64, mac Intel, mac ARM, linux…) à builder, idéalement sur chaque OS (CI GitHub Actions fait ça bien) |
| Script d'install (pipx, uv) | très faible | mieux que le clone git, mais Python requis |
| Stores (Steam/itch natif) | élevé | visibilité, mais signature macOS (~99 $/an), SmartScreen Windows sans certificat… |

### Avantages
- **Performances pleines** : c'est la version où la carte géante, les
  8 joueurs et les grosses batailles tournent. Le portable lent y gagne aussi.
- **Réseau libre** : LAN actuel intact (TCP + découverte UDP), Tailscale qui
  marche déjà, relais optionnel — pas d'infra obligatoire.
- **Débogage/outillage** : profiling, tests headless, tout l'existant.

### Inconvénients
- **La matrice multiplateforme est une vraie charge** : 4-6 binaires à
  builder/tester à chaque version, Gatekeeper macOS qui bloque les binaires
  non signés (contournable mais rebutant pour un invité), antivirus Windows
  parfois suspicieux avec PyInstaller.
- **Friction d'installation** : télécharger 60-80 Mo, « fichier non
  reconnu », etc. Chaque étape perd des joueurs.
- **Fragmentation des versions** en lockstep : deux joueurs sur des builds
  différents = désync. Il faut un contrôle de version au handshake (le champ
  existe dans `hello` ? à ajouter sinon — bonne idée dans tous les cas).

## 3. Les fausses pistes (regardées, écartées)

- **Réécriture web native (JS/Phaser/Godot)** : le double du travail, deux
  sims à maintenir, perte du déterminisme partagé. Non.
- **Cloud gaming / streaming du jeu** : serveur GPU par joueur, coût et
  latence absurdes pour un jeu 2D. Non.
- **Electron + Python embarqué** : cumule les inconvénients (poids du
  navigateur + packaging natif). Non.

## 4. Recommandation : les deux, dans cet ordre

Ne pas choisir « navigateur OU natif » — les deux partagent 95 % du code et
la même brique serveur :

1. **Court terme (0 code)** : natif + Tailscale pour jouer avec l'extérieur
   dès maintenant (rapport 01-A).
2. **Moyen terme (~1 j + VPS 4 €)** : serveur **relais WebSocket avec codes de
   partie**, utilisé d'abord par le natif (`PeerWS`). C'est l'investissement
   pivot : il sert immédiatement (Internet sans ports) et prépare le web.
3. **Ensuite (~2-3 j)** : build **pygbag** en « démo accessible » — solo +
   multi web↔web sur cartes petites/moyennes, publiée sur itch.io. Le natif
   reste la version « complète » (grandes cartes, LAN, perfs).
4. **Plus tard, si le jeu prend** : binaires PyInstaller via GitHub Actions
   pour ceux qui veulent le natif sans Python, matchmaking natif↔web
   seulement après validation du déterminisme croisé (rapport 02 §2.5).

Le point à retenir : **le relais WebSocket est le seul morceau
d'infrastructure réellement nécessaire, et il sert les deux mondes**. Tout le
reste est du packaging.
