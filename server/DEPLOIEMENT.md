# Déployer le relais CRISTALIS sur un VPS

Le relais (`relay.py`) est un unique fichier Python sans dépendance (stdlib
uniquement, Python ≥ 3.8). N'importe quel VPS Linux à ~4 €/mois suffit
largement (Hetzner CX22, OVH, Scaleway…) — choisir un datacenter proche des
joueurs (Paris/Francfort depuis la France). Seules les commandes des joueurs
transitent : quelques centaines d'octets par seconde et par partie.

## Installation (une fois, en root sur le VPS)

```bash
# utilisateur dédié sans shell ni home
useradd --system --no-create-home --shell /usr/sbin/nologin cristalis

# le relais et son service
mkdir -p /opt/cristalis
curl -fsSL https://raw.githubusercontent.com/bastien313/CRISTALIS/master/server/relay.py \
     -o /opt/cristalis/relay.py
curl -fsSL https://raw.githubusercontent.com/bastien313/CRISTALIS/master/server/cristalis-relay.service \
     -o /etc/systemd/system/cristalis-relay.service

systemctl daemon-reload
systemctl enable --now cristalis-relay

# pare-feu : ouvrir le port du relais (selon l'outil du VPS)
ufw allow 45456/tcp        # si ufw est utilisé
```

## Vérifier

```bash
systemctl status cristalis-relay      # doit être « active (running) »
journalctl -u cristalis-relay -f      # log : « Relais CRISTALIS en écoute… »
```

Depuis un PC : lancer le jeu avec `CRISTALIS_RELAY=IP_DU_VPS`, choisir
**Héberger (Internet)** — un code de partie doit s'afficher.

## Brancher le jeu dessus

Deux options :

- variable d'environnement : `CRISTALIS_RELAY=IP_DU_VPS` (ou `IP:port` si le
  port n'est pas 45456) avant de lancer `python cristalis.py` ;
- ou en dur : remplacer la valeur par défaut de `RELAY_ADDR` dans
  `netcode.py` (recommandé une fois le VPS stable, pour que les amis n'aient
  rien à configurer).

## Mettre à jour le relais

```bash
curl -fsSL https://raw.githubusercontent.com/bastien313/CRISTALIS/master/server/relay.py \
     -o /opt/cristalis/relay.py
systemctl restart cristalis-relay
```

(Les parties en cours passent par des connexions déjà appariées : un restart
les coupe — à faire hors des heures de jeu.)

## Notes

- Aucune donnée n'est stockée sur le VPS : le relais ne fait que mettre en
  relation deux connexions et faire suivre les octets.
- Le service est durci (utilisateur dédié, système en lecture seule,
  mémoire plafonnée) : voir `cristalis-relay.service`.
- Si le VPS a IPv6 seulement en plus de l'IPv4, rien à faire : le relais
  écoute en 0.0.0.0 (IPv4) ; les joueurs utilisent l'IPv4 du VPS.
