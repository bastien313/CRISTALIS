# CRISTALIS — La Guerre des Cristaux

Un jeu de stratégie en temps réel (RTS) en Python / pygame.
1v1 contre l'IA **ou contre un ami en LAN** : **le premier qui détruit tous les
bâtiments de l'autre gagne.**

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

## Commandes

| Action | Commande |
|---|---|
| Sélectionner | Clic gauche / rectangle de sélection (Maj = ajouter) |
| Ordre (déplacer, attaquer, récolter, construire) | Clic droit |
| Attaque-déplacement | `A` puis clic |
| Groupes de contrôle | `Ctrl+1..5` enregistrer, `1..5` rappeler |
| Caméra | Flèches, bord de l'écran, clic sur la minimap |
| Pause / Aide | `P` / `F1` |

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

La baliste tire de plus loin que la Tour de cristal (235 contre 190) : c'est
l'arme idéale pour percer une base fortifiée, mais elle est fragile — escortez-la.

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

## IA

Trois difficultés (Facile / Normal / Difficile). L'IA gère son économie,
étend sa base, construit des défenses, recherche des améliorations et lance
des vagues d'attaque de plus en plus grosses.

## Test automatique

```
python cristalis.py --autotest
```

Simule une partie IA contre IA sans fenêtre et affiche le vainqueur.
