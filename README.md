# CRISTALIS — La Guerre des Cristaux

*Version 0.18* — la version courante s'affiche au menu principal et dans le titre
de la fenêtre.

Un jeu de stratégie en temps réel (RTS) en Python / pygame.
De **2 à 8 joueurs**, en solo contre l'IA ou **avec des amis en LAN ou par
Internet** (via un petit serveur relais et un code de partie), seul ou
**en équipes** (avec des zombies optionnels) : **la dernière équipe qui garde au
moins un bâtiment debout gagne.**

Quatre tailles de cartes, de la petite escarmouche à la **carte géante**
(512×256 cases) : le fond est généré par morceaux à la demande, la taille de
la carte ne pèse donc ni sur la mémoire ni sur le temps de lancement.

Direction artistique « pré-rendu » façon RTS des années 2000 : tous les sprites
(unités orientées sur 16 directions, bâtiments détaillés, arbres, interface à
panneaux biseautés) sont peints procéduralement au lancement (`art.py`) —
aucune image externe. Ombres portées, lueurs additives, fumées, explosions,
cadavres et décombres qui s'estompent. Brouillard de guerre : le terrain non
exploré est noir, les zones déjà vues restent visibles en sombre.

## Lancer le jeu

```
python cristalis.py
```

(nécessite `pip install pygame`, et `numpy` en option pour les effets sonores)

## Multijoueur en LAN

Dans le menu principal :

1. Sur la première machine, choisissez **Héberger (LAN)** — votre adresse IP
   s'affiche à l'écran.
2. Sur la seconde, choisissez **Rejoindre (LAN)** : les parties hébergées sur le
   réseau local sont détectées automatiquement (sinon, tapez l'adresse IP de
   l'hôte et validez avec Entrée).

L'hôte joue l'Ordre d'Azur (bleu), l'invité la Légion Karmin (rouge). La partie
utilise une simulation en *lockstep* : seules les commandes des joueurs
transitent par le réseau (TCP, port 45455 ; découverte UDP, port 45454).
Utilisez de préférence la même version de Python sur les deux machines. `P`
met la partie en pause pour les deux joueurs.

Le champ d'adresse accepte aussi `ip:port`, pratique pour rejoindre un hôte
exposé derrière un tunnel (playit.gg, ngrok…).

## Multijoueur par Internet

Aucun port à ouvrir sur les box : les deux joueurs se connectent **en sortant**
vers un petit serveur relais (`server/relay.py`, stdlib uniquement) hébergé sur
un VPS.

1. Sur le VPS : `python server/relay.py` (port 45456 par défaut) — service
   systemd fourni et pas-à-pas complet dans
   [server/DEPLOIEMENT.md](server/DEPLOIEMENT.md), la consommation est
   dérisoire (seules les commandes des joueurs transitent).
2. Dans le jeu, pointez le relais via la variable d'environnement
   `CRISTALIS_RELAY` (`ip` ou `ip:port`) ou la constante `RELAY_ADDR` de
   `netcode.py`.
3. L'hôte choisit **Héberger (Internet)** : un **code de partie** s'affiche
   (ex. `AZUR-7`). L'invité choisit **Rejoindre (Internet)** et entre le code.

Au handshake, l'hôte mesure la latence et adapte automatiquement le délai
lockstep (`NET_DELAY`, de 150 à 600 ms) — la même valeur est utilisée des deux
côtés. En partie, un battement de cœur applicatif détecte les connexions
mortes en ~10 s au lieu des minutes du timeout TCP.

## Commandes

| Action | Commande |
|---|---|
| Sélectionner | Clic gauche / rectangle de sélection (Maj = ajouter) |
| Ordre (déplacer, attaquer, récolter, construire) | Clic droit |
| Attaque-déplacement | `A` puis clic |
| Groupes de contrôle | `Ctrl+1..5` enregistrer, `1..5` rappeler |
| Annuler un placement / désélectionner / menu pause | `Échap` |
| Caméra | Flèches, bord de l'écran, clic sur la minimap |
| Pause / Aide | `P` / `F1` |

En partie, `Échap` (sans sélection ni placement en cours) ou `P` ouvre le menu
pause : **REPRENDRE** pour continuer, **QUITTER** pour confirmer le retour au
menu d'accueil. Sur l'écran de fin, `Échap` ramène aussi au menu.

## Économie

- Les **ouvriers** récoltent les **cristaux** et les déposent au **Quartier Général**.
- Le QG produit des ouvriers (`O`).
- Un ouvrier sélectionné peut construire : QG `G`, Obélisque `O`, Caserne `C`,
  Archerie `R`, Forge `F`, Tour de cristal `T`, Sanctuaire `S`, Muraille `M`,
  Porte `E`.
- Les **Obélisques** augmentent le ravitaillement (limite d'unités).

## Unités

| Unité | Bâtiment | Coût | PV | ATQ | Portée | Vitesse | Cadence | Ravit. | Rôle |
|---|---|---|---|---|---|---|---|---|---|
| Ouvrier `O` | QG | 50 | 45 | 4 | 16 | 82 | 1,0 s | 1 | Récolte et construit |
| Soldat `S` | Caserne | 75 | 105 | 10 | 20 | 74 | 0,85 s | 1 | Mêlée robuste, bon marché |
| Archer `A` | Archerie | 110 | 55 | 9 | 150 | 68 | 1,05 s | 1 | Dégâts à distance |
| Mage cristallin `M` | Archerie | 165 | 50 | 20 | 165 | 58 | 2,3 s | 2 | Dégâts de zone (rayon 44) |
| Golem de quartz `G` | Forge | 240 | 350 | 25 | 24 | 45 | 1,35 s | 3 | Tank lourd de première ligne |
| Baliste `B` | Forge | 230 | 95 | 28 (**×3 vs bâtiments**) | 235 | 44 | 3,2 s | 3 | Engin de siège, surclasse les tours |
| **Maelan** `N` | Caserne | 450 | 200 | 20 | 20 | 100 | 0,6 s | 3 | Ninja d'élite : rapide comme le vent, frappe sans répit |
| **Adryann** `Y` | Caserne | 420 | 200 | 20 | 20 | 60 | 1,0 s | 3 | Bouboule vorace : dévore ses victimes (+10 % PV max) |

La baliste tire de plus loin que la Tour de cristal (235 contre 190) : c'est
l'arme idéale pour percer une base fortifiée, mais elle est fragile — escortez-la.

**Champions d'élite** (débloqués à la Caserne) : *Maelan* est un petit ninja
foudroyant qui enchaîne près de deux coups par seconde ; *Adryann*, la bouboule
vorace, engloutit chaque victime — il ne laisse ni cadavre ni tombe, gagne
+10 % de PV max à chaque repas… et sème parfois un petit cadeau en chemin.

## Bâtiments

| Bâtiment | Touche | Coût | PV | Taille | Chantier | Rôle |
|---|---|---|---|---|---|---|
| Quartier Général | `G` | 400 | 950 | 4×3 | 45 s | Dépôt de cristaux, produit les ouvriers, +10 ravit. |
| Obélisque | `O` | 100 | 260 | 1×2 | 13 s | +8 de ravitaillement |
| Caserne | `C` | 150 | 550 | 3×2 | 20 s | Forme les soldats |
| Archerie | `R` | 180 | 480 | 3×2 | 24 s | Forme archers et mages |
| Forge à golems | `F` | 260 | 650 | 3×3 | 30 s | Assemble golems et balistes |
| Tour de cristal | `T` | 130 | 380 | 2×2 | 17 s | Défense auto : ATQ 13, portée 190, cadence 0,95 s |
| Sanctuaire | `S` | 200 | 500 | 2×2 | 22 s | Recherche les améliorations ATQ / DEF |
| Muraille | `M` | 25 | 260 | 1×1 | 6 s | Rempart infranchissable ; les segments se posent bord à bord |
| Porte | `E` | 50 | 240 | 1×1 | 8 s | **Ne s'ouvre que pour les unités de son propriétaire** |

## Améliorations (Sanctuaire)

| Recherche | Touche | Coût | Durée | Effet (cumulable, 3 niveaux) |
|---|---|---|---|---|
| Attaque | `A` | 150 | 25 s | Dégâts de **vos unités** +15 % par niveau |
| Défense | `D` | 150 | 25 s | Dégâts subis par **vos unités** −12 % par niveau |

## Fortifications

Les murailles se construisent segment par segment (maintenez `Maj` en cliquant
pour en poser plusieurs d'affilée). La porte s'ouvre automatiquement à
l'approche d'une de **vos** unités et se referme derrière elle ; les ennemis
doivent la détruire pour passer.

## Brouillard de guerre

Chaque joueur ne voit que ce que ses unités et bâtiments éclairent. Les zones
déjà explorées restent visibles en sombre (avec les bâtiments ennemis repérés),
mais les unités ennemies n'y sont plus affichées. La minimap suit les mêmes
règles.

En fin de partie, le brouillard est désactivé pour révéler toute la carte.

## IA

Trois difficultés (Facile / Normal / Difficile), chacune avec un style propre.

- **Facile** : économie modeste et lente, tech volontairement limitée
   (obélisque, caserne, archerie), armée légère (soldats/archers), petites
   vagues espacées, petite garnison locale qui revient défendre la base.
- **Normal** : économie robuste (plus d'ouvriers), tech complète, obélisques
   optimisés pour soutenir la population, armée mixte avec troupes de base et
   élites, ciblage prioritaire des unités dangereuses, repli stratégique quand
   la force engagée tombe sous la moitié, garnison défensive (archers + tours).
- **Difficile** : économie agressive avec expansion par QG périphériques près
   des gisements, tech complète + améliorations, production soutenue en
   escouades, ciblage tactique des menaces majeures, repli/réengagement par
   vagues, fortifications denses (nombreuses tours, murailles) et garnison de
   mages ; renforts rapides en cas d'attaque sur la base.

## Mode Survie zombie

Un quatrième mode est disponible dans le menu de difficulté : **Survie zombie**.

- Un écran **Configuration Survie zombie** permet de choisir :
   - la carte (**petite**, **moyenne**, **grande**, **géante**),
   - le temps entre deux nouveaux zombies (curseur **5s à 120s**),
   - le délai avant le début de l'invasion (curseur **0 à 10 minutes**).
- Votre base démarre **au centre de la carte**.
- Objectif : survivre le plus longtemps possible.
- Une phase de préparation est affichée selon la valeur choisie avant l'invasion.
- À `00:00`, le message **« Les zombies arrivent ! »** s'affiche et le chrono de survie démarre.
- Défaite en Survie : dès que votre **Quartier Général** est détruit.
- Le chrono de partie est affiché comme score, et les sessions sont enregistrées
   dans `survival_scores.json` (record affiché en jeu).
- Aucun zombie n'est présent au démarrage de la partie.
- À l'intervalle configuré, un nouveau zombie entre par un bord de carte.
- Si un zombie meurt, un remplaçant revient immédiatement pour conserver la pression.
- Les zombies se déplacent aléatoirement sur la carte.
- Quand des zombies se rencontrent, ils se regroupent et partagent une destination,
   formant des hordes.

## Tests automatiques

```
python cristalis.py --autotest   # partie IA contre IA sans fenêtre
python test_features.py          # suite de tests headless (Survie, pause, déterminisme, relais…)
```
