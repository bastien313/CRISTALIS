# Rapports réseau — CRISTALIS (branche `reseau`)

Brainstorm du 2026-07-07 : comment faire jouer des gens **hors du réseau
local**, et faut-il viser le **navigateur** ou le **natif**. Trois rapports :

| Rapport | Question |
|---|---|
| [01 — Internet sans ouvrir de ports](01-internet-sans-ouvrir-de-ports.md) | Jouer avec quelqu'un d'extérieur au LAN, sans toucher à la box |
| [02 — Version navigateur](02-version-navigateur.md) | Faire tourner ce code Python dans un navigateur (brief détaillé pour un autre LLM) |
| [03 — Navigateur vs natif](03-navigateur-vs-natif.md) | Tour d'horizon : accessibilité web contre maîtrise du natif |

## Synthèse (TL;DR)

Le point clé qui structure tout : le netcode actuel (`netcode.py`) est du
**TCP JSON en lockstep**, ~170 lignes, bien isolé derrière la classe `Peer`
(`send` / `poll` / `alive` / `close`). Tout ce qui suit revient à brancher un
autre transport derrière cette même interface — la sim n'a jamais besoin de
changer.

- **Ce week-end, zéro ligne de code** : Tailscale (VPN maillé gratuit) — ton
  ami installe l'appli, rejoint ton réseau, tape ton IP `100.x.y.z` dans
  « Rejoindre (LAN) ». Ça marche aujourd'hui, sans ouvrir de port.
- **Étape suivante, ~1 journée de dev + un VPS à 4 €/mois** : un petit
  serveur relais avec codes de partie (« donne le code `AZUR-7` à ton ami »).
  UX propre, aucun logiciel tiers, et c'est le même relais qui servira à une
  éventuelle version web.
- **Version navigateur (pygbag/WebAssembly)** : faisable et c'est la voie
  royale pour l'accessibilité (une URL, zéro installation), mais c'est un
  chantier : boucle de jeu à passer en `async`, netcode à passer en
  WebSocket, performances ×2-5 plus lentes (cartes géantes à proscrire au
  début). Détail complet dans le rapport 02.
- **Recommandation navigateur vs natif** : ne pas choisir — garder le natif
  comme version de référence (LAN, perfs, grandes cartes) et ajouter une
  build web comme « démo jouable » qui partage le même relais. Les deux
  mondes ne peuvent de toute façon pas jouer l'un contre l'autre sans
  vérifier le déterminisme croisé (cf. rapport 02, § déterminisme).
