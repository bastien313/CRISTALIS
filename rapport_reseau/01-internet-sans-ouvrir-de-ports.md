# 01 — Jouer par Internet sans ouvrir de ports sur la box

## Le problème

Le LAN actuel : l'hôte écoute en TCP sur le port 45455 (`HostListener`), le
client s'y connecte (`connect(ip)`), la découverte se fait en broadcast UDP
45454 (LAN uniquement, par construction). Par Internet, deux obstacles :

1. **NAT** : la box de l'hôte ne route pas les connexions entrantes vers son
   PC sans redirection de port (ce qu'on veut justement éviter).
2. **Découverte** : le broadcast UDP ne traverse jamais Internet — il faudra
   toujours échanger une adresse ou un code de partie.

La bonne nouvelle : quand **les deux machines se connectent en sortant**
(vers un service tiers), aucun port à ouvrir nulle part. Toutes les solutions
ci-dessous exploitent ça.

## Option A — VPN maillé « zéro config » : Tailscale (recommandé pour commencer)

**Principe** : Tailscale (basé WireGuard) crée un réseau privé virtuel entre
tes machines et celles de tes invités. Chacun installe l'appli, se connecte au
même « tailnet » (tu invites ton ami par mail/lien), et chaque machine reçoit
une IP stable en `100.x.y.z`. Pour les applis, c'est **comme si vous étiez
sur le même LAN**.

- **Changement de code : zéro.** Ton ami tape ton IP Tailscale dans
  « Rejoindre (LAN) » (la saisie manuelle existe déjà). Seule la découverte
  automatique UDP ne fonctionnera pas — c'est cosmétique.
- Traversée de NAT automatique (hole punching), et repli sur leurs relais
  (DERP) si les NAT sont trop stricts. Gratuit pour l'usage perso
  (plan « Personal » : ~3 utilisateurs, 100 machines — à re-vérifier, ça
  évolue). Alternatives équivalentes : **ZeroTier** (auto-hébergeable),
  Hamachi (vieillissant, éviter).
- **Avantages** : disponible aujourd'hui, chiffré, réutilisable pour tout
  (partage de fichiers, SSH…). Latence quasi optimale en connexion directe.
- **Inconvénients** : chaque joueur doit installer un logiciel et être invité
  → très bien entre amis, inadapté pour faire jouer des inconnus. Compte
  requis (login Google/GitHub/MS).

**Verdict** : la solution du week-end. C'est ce que je testerais en premier.

## Option B — Tunnel côté hôte : playit.gg / ngrok / bore

**Principe** : l'hôte lance un petit client de tunnel qui expose son port
45455 via un serveur public du service. L'invité n'installe **rien** : il se
connecte à l'adresse publique fournie (ex. `xyz.playit.gg:12345`).

- **playit.gg** : pensé pour les jeux (Minecraft…), tunnel TCP/UDP gratuit,
  adresse réutilisable. **ngrok** : tunnel TCP gratuit mais adresse/port
  aléatoires à chaque lancement. **bore / rathole / frp** : auto-hébergés
  (il faut alors… un serveur, cf. option C).
- **Changement de code : minime mais réel** — le port distant n'est plus
  45455 : il faut accepter `hôte:port` dans l'écran « Rejoindre » et le
  passer à `connect()` (aujourd'hui le port est une constante). ~20 lignes.
- **Avantages** : rien à installer côté invité, pas de compte pour lui.
- **Inconvénients** : dépendance à un service tiers (gratuit ⇒ pérennité non
  garantie), latence : tout le trafic passe par leur relais (souvent
  Francfort/Amsterdam depuis la France, +10-30 ms — acceptable pour du
  lockstep à 20 Hz). L'hôte doit installer et lancer le client de tunnel.

**Verdict** : bon plan B sans code serveur à écrire, si l'ami ne veut rien
installer. Prévoir la modif `hôte:port` de toute façon — elle est utile
partout.

## Option C — Ton propre serveur relais + codes de partie (la vraie solution)

**Principe** : un petit serveur (VPS) accepte des connexions TCP/WebSocket
**sortantes** des deux joueurs. L'hôte crée une partie → le serveur renvoie
un code court (`AZUR-7`). L'invité entre le code → le serveur met les deux
connexions en relation et **fait suivre les octets** dans les deux sens. Ni
l'un ni l'autre n'ouvre de port.

- **Côté serveur** : ~100-150 lignes de Python (asyncio) : tenir un dict
  `code → connexion en attente`, puis pomper les lignes JSON d'une socket à
  l'autre. Aucune logique de jeu — le lockstep s'en fiche, il ne voit qu'un
  tuyau.
- **Côté jeu** : nouvelle entrée de menu « Partie Internet » : héberger →
  affiche le code ; rejoindre → champ code. La classe `Peer` est réutilisée
  telle quelle (c'est toujours une socket TCP) ; seul l'établissement de la
  connexion change (~50 lignes dans `netcode.py` + un écran dans `menus.py`).
- **Hébergement** : n'importe quel VPS à ~4 €/mois (Hetzner CX22,
  Scaleway/OVH équivalents), ou l'« Always Free » d'Oracle Cloud (gratuit,
  mais capricieux). Conso dérisoire : le lockstep n'envoie que les commandes
  (quelques centaines d'octets/s par partie) — un VPS minuscule tient des
  centaines de parties.
- **Avantages** : UX idéale (un code à dicter), aucun logiciel tiers, aucune
  inscription, tu maîtrises tout, et **c'est la même brique qui servira à la
  version navigateur** (rapport 02) si on la fait parler WebSocket d'entrée.
- **Inconvénients** : ~1 journée de dev + un serveur à maintenir ; +latence
  du double trajet via le VPS (choisir un datacenter proche des joueurs,
  Paris/Francfort ⇒ +5-20 ms, négligeable à 20 ticks/s).

**Verdict** : l'investissement le plus rentable si le jeu doit sortir du
cercle d'amis. À faire en WebSocket plutôt qu'en TCP brut pour préparer le web.

## Option D — Traversée de NAT (hole punching) : à éviter ici

Le « vrai » P2P sans relais : un serveur de rendez-vous échange les adresses
publiques des deux joueurs, qui ouvrent des connexions simultanées pour
percer leurs NAT. Problèmes : le hole punching **TCP** est peu fiable
(~60-70 % des cas) ; en UDP il faudrait réécrire le transport (fiabilité,
ordre — le lockstep exige les deux) ; et il faut de toute façon un serveur de
rendez-vous + un relais de secours… c'est-à-dire l'option C avec des
complications. C'est ce que font Steam Networking ou WebRTC, mais autant leur
laisser cette complexité. **Non recommandé** pour CRISTALIS en Python natif.

## Contraintes lockstep à garder en tête (quel que soit le choix)

- `NET_DELAY = 3` ticks à 20 Hz = les commandes partent 150 ms avant leur
  exécution : un ping < 150 ms est invisible, au-delà la sim « attend
  l'adversaire » (le message existe déjà). Europe↔Europe : aucun souci ;
  Europe↔Amérique : prévoir un `NET_DELAY` adaptatif (mesurer le RTT au
  handshake et l'envoyer dans `hello`).
- TCP suffit : à 20 Hz avec quelques commandes par tick, la retransmission
  sur perte de paquet coûte un léger à-coup, pas plus. Pas besoin d'UDP.
- La découverte UDP reste LAN : par Internet, c'est adresse manuelle (A/B)
  ou code de partie (C).

## Comparatif

| | Code à écrire | Install. invité | Service tiers | Coût | Pour qui |
|---|---|---|---|---|---|
| **A. Tailscale** | aucun | oui (appli+compte) | oui | 0 € | entre amis, tout de suite |
| **B. playit.gg** | ~20 lignes (`hôte:port`) | non | oui | 0 € | amis, hôte motivé |
| **C. Relais + code** | ~1 jour | non | non (le tien) | ~4 €/mois | ouvrir le jeu à tous |
| **D. Hole punching** | beaucoup | non | rendez-vous | ~4 €/mois | pas rentable ici |

**Ordre conseillé : A aujourd'hui → C ensuite (en WebSocket), B en secours.**
