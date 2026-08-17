# Synchronisation Docs → Obsidian

**Date** : 2026-08-14
**Statut** : validé, prêt pour implémentation

## Objectif

Répliquer l'arborescence d'un document Docs (parent + tous ses descendants) dans un vault
Obsidian local, en ne téléchargeant que ce qui a réellement changé depuis la dernière
synchronisation.

Usage visé : sauvegarde textuelle locale des documents produits que Louis suit (Hub,
Console), déclenchée soit à la demande dans une conversation, soit par une skill de routine
qui appellera le tool MCP.

## Périmètre

**Dans** : sens Docs → vault uniquement, arbre complet à partir d'une racine, détection des
changements par date, réécriture des liens inter-documents en wikilinks, rapport de
synchronisation.

**Hors** : sens vault → Docs, téléchargement des images et pièces jointes, merge de
modifications locales, CLI, job planifié. Chacun de ces points est traité en fin de document.

## Faits mesurés sur l'API

Sondages en lecture seule contre `https://docs.numerique.gouv.fr` le 2026-08-14, sur
l'arbre `🐙 LaSuite - Équipe Hub` (`5b243392-b3a5-4caa-a7e6-e88566e1c72e`).

| Fait | Conséquence sur le design |
|------|---------------------------|
| `GET /documents/{id}/tree/` renvoie l'arbre de la **racine ancestrale**, avec seulement le chemin vers le document demandé déplié. Les nœuds frères arrivent avec `children: []` malgré un `numchild` non nul. | Inutilisable pour une découverte de sous-arbre. On marche récursivement avec `/children/`. |
| `GET /documents/{id}/children/` est paginé et non récursif. | Descente niveau par niveau, appels parallélisés à chaque niveau. |
| `GET /documents/{id}/descendants/` renvoie 404 malgré `abilities.descendants: true`. | Route absente en production, non utilisable. |
| La liste plate `/documents/` ne renvoie que les documents sur lesquels l'utilisateur a un accès **direct** (191 sur ce compte). Filtrer par préfixe de `path` ne retrouve que 1 des 129 nœuds du Hub. | Pas de raccourci par la liste plate. |
| `updated_at` est présent sur chaque nœud renvoyé par `/children/`. | La décision « faut-il retélécharger » se prend sans lire aucun contenu. |
| `GET /documents/{id}/formatted-content/?content_format=markdown` n'expose ni `ETag` ni `Last-Modified`. | Pas de GET conditionnel. Le contenu se récupère en entier ou pas du tout. |
| Le corps markdown ne contient pas le titre. | Le titre vit dans le nom de fichier et le frontmatter, pas en H1. |
| Les liens inter-documents sortent sous la forme `https://docs.numerique.gouv.fr/docs/<uuid>/`. | Réécriture en wikilinks possible par simple substitution. |
| Les images pointent vers `/media/<uuid>/attachments/…`, URLs authentifiées. | Hors périmètre, laissées telles quelles ; elles ne s'afficheront pas dans Obsidian. |

Coûts mesurés sur l'arbre Hub (129 documents, profondeur 5) :

```
découverte récursive     : 28 requêtes,  ~1-6 s,   aucun contenu téléchargé
première synchronisation : + 129 requêtes, 1,4 Mo, ~10 s au total
synchronisation courante : + N requêtes (N = documents modifiés), ~2 s
```

Contraintes de nommage relevées sur ce même arbre : aucun titre dupliqué sur 129 documents,
chemin le plus long 189 octets sur 6 niveaux, nom de fichier le plus long 83 octets.
Caractères à traiter : `/` et `:` dans 6 titres, espaces de largeur nulle (U+200B, U+200D)
dans 3 titres.

L'absence de doublons est ce qui rend les wikilinks fiables : Obsidian résout `[[nom]]` par
nom de fichier, indépendamment du dossier.

## Modèle de données

L'identité d'un document dans le vault est son UUID, porté par le frontmatter du fichier —
jamais son chemin ni son nom. Un document renommé ou déplacé dans Docs reste le même fichier.

```yaml
---
docs_id: 5b243392-b3a5-4caa-a7e6-e88566e1c72e
docs_url: https://docs.numerique.gouv.fr/docs/5b243392-b3a5-4caa-a7e6-e88566e1c72e/
docs_title: "🐙 LaSuite - Équipe Hub"
docs_updated_at: 2026-07-01T09:12:44.812340Z
docs_synced_at: 2026-08-14T15:02:00Z
---
```

`docs_title` conserve le titre exact, y compris les caractères que le nom de fichier a dû
assainir. `docs_updated_at` est la valeur renvoyée par l'API au dernier téléchargement : c'est
elle, et non la mtime du fichier, qui sert de point de comparaison — la mtime bouge dès
qu'Obsidian ou git touche le fichier.

**Le frontmatter est manipulé ligne à ligne, pas via un parseur YAML.** À la mise à jour, les
lignes dont la clé commence par `docs_` sont remplacées ; toutes les autres sont recopiées
verbatim. Les propriétés que Louis ajoute lui-même dans Obsidian (tags, statut, commentaires
YAML) survivent donc aux synchronisations, sans introduire de dépendance YAML ni perdre
l'ordre et les commentaires à chaque round-trip.

Aucun hash du contenu n'est stocké : le vault n'est pas source de vérité, un document dont la
date a bougé est réécrit sans condition.

## Arborescence dans le vault

Convention *folder note* : un document ne devient un dossier que s'il a des enfants.

```
Docs/🐙 LaSuite - Équipe Hub/
├── 🐙 LaSuite - Équipe Hub.md          corps de la racine
├── 📆 Roadmap 2026.md                  feuille
├── 💜 Feedbacks - intérêt Hub.md       « / » assaini en « - »
├── 🔮 Vision produit/
│   ├── 🔮 Vision produit.md
│   └── Nom du produit - Tchap vs. New.md
└── 🦕 Archives/
    └── 🦕 Archives.md                  corps vide, mais porte le docs_id
```

Règle : `numchild == 0` → `<dossier>/<nom>.md` ; `numchild > 0` → `<dossier>/<nom>/<nom>.md`,
les enfants étant placés dans `<dossier>/<nom>/`. Un parent au corps vide reçoit quand même
son fichier : il porte son `docs_id` et pourra recevoir du contenu plus tard sans
réorganisation.

Assainissement du nom de fichier, dans cet ordre :

1. suppression des caractères de largeur nulle (U+200B, U+200C, U+200D, U+FEFF)
2. remplacement de `/ \ : * ? " < > |` par `-`
3. normalisation des espaces (séquences → un seul, puis strip), suppression des points en fin
4. troncature à 120 octets UTF-8, sans couper un caractère
5. chaîne vide en sortie → `sans-titre`

Les emojis sont conservés : macOS et Obsidian les gèrent, et ils portent du sens dans ce vault.

Collision entre frères après assainissement (`A/B` et `A-B` donnent tous deux `A-B`) : les
frères sont triés par leur `path` matérialisé, le premier garde le nom, les suivants reçoivent
un suffixe ` (2)`, ` (3)`. Le `path` étant stable côté serveur, la résolution est
déterministe d'une exécution à l'autre.

## Algorithme

```
1. Résoudre la racine
   URL ou UUID → GET /documents/{id}/  (titre, updated_at, numchild)

2. Découvrir l'arbre
   BFS via /children/, un niveau à la fois, appels du niveau parallélisés.
   Pagination suivie jusqu'à `next: null`. Aucun contenu téléchargé.

3. Calculer la disposition cible
   Pour chaque nœud : chemin relatif, selon la règle folder note et l'assainissement.

4. Indexer l'existant
   Parcours des .md de tout le vault, lecture du frontmatter, index docs_id → chemin.
   Un fichier sans docs_id est une note personnelle : ignoré, jamais touché.

   L'index couvre le vault entier, pas la seule destination : un document déjà miroité
   ailleurs (typiquement dans un arbre plus large synchronisé auparavant) doit être
   rafraîchi là où il vit, et non dupliqué sous la destination demandée. `destination` ne
   décide donc que du placement des documents encore absents.

   Corollaire : le dossier « possédé » par l'exécution — celui qui contient la note de la
   racine — délimite ce qui suit la disposition calculée. Une note à l'intérieur suit le
   layout (renommages et reparentages la déplacent) ; une note à l'extérieur est mise à jour
   sur place. Une racine sans enfant ne possède aucun dossier, sans quoi elle revendiquerait
   toute la destination.

5. Classer chaque nœud
   absent de l'index                          → CRÉÉ     (télécharger, écrire)
   présent, docs_updated_at identique,
       et chemin cible identique              → INCHANGÉ (aucune requête)
   présent, chemin cible différent            → DÉPLACÉ  (+ mis à jour si la date a bougé)
   présent, docs_updated_at différent         → MIS À JOUR (télécharger, réécrire)

6. Détecter les orphelins
   Fichier indexé, situé dans le dossier possédé par l'exécution, dont le docs_id n'est plus
   dans l'arbre : signalé, jamais touché. Les notes d'un autre miroir ailleurs dans le vault
   ne regardent pas cette exécution.

7. Écrire
   Téléchargements parallélisés sous le sémaphore du client.
   Réécriture des liens, composition du frontmatter, écriture atomique.
   Suppression des dossiers devenus vides dans le dossier possédé par l'exécution.
```

### Règle d'écriture : un emplacement occupé n'est jamais écrasé

Le classement de l'étape 5 travaille sur l'index pris **avant** l'exécution, alors que l'étape 7
modifie le disque. Un chemin cible calculé comme libre peut donc être occupé : par un orphelin,
par une note personnelle, ou par un frère qui n'a pas encore quitté ce nom. `Path.replace` et
l'écriture atomique écrasent tous deux sans prévenir, et le fichier détruit ne serait signalé
nulle part.

D'où la règle, appliquée au moment du classement pour que `dry_run` la remonte aussi :

> On n'écrit à un emplacement que s'il est libre, ou s'il porte déjà la note de ce document.

Sinon le document est ignoré et l'incident part dans `errors` avec `reason: target_occupied` et
le chemin. Un nom pris par un document qui déménage se libère dès que ce déplacement aboutit :
l'exécution suivante termine ce que celle-ci a laissé. Deux documents qui échangent leurs titres
se bloquent mutuellement et restent signalés jusqu'à ce qu'un des deux fichiers soit renommé à
la main — une erreur stable et honnête vaut mieux que détruire une note pour départager.

La suppression des dossiers vides est bornée au dossier possédé par l'exécution, et non à toute
la destination : les dossiers vides que l'utilisateur garde ailleurs ne regardent pas cette
synchronisation. Avec `destination: "."` la portée aurait été le vault entier.

En `dry_run`, les étapes 1 à 6 s'exécutent normalement et l'étape 7 est remplacée par la
production du rapport. Aucune écriture, aucun téléchargement de contenu.

### Réécriture des liens

Après téléchargement, les URLs `https://<base_url>/docs/<uuid>/` dont l'UUID appartient à
l'arbre synchronisé sont remplacées :

- `[texte](url)` → `[[nom|texte]]`, ou `[[nom]]` si `texte` est déjà le titre de la cible
- URL nue → `[[nom]]`

où `nom` est le nom de fichier assaini de la cible, sans extension. Les liens vers des
documents hors de l'arbre et les URLs `/media/` sont laissés intacts.

### Écriture atomique

Écriture dans un fichier temporaire du même dossier puis `os.replace`. Une synchronisation
interrompue ne laisse pas de fichier tronqué dans le vault.

## Sécurité

Le serveur MCP n'a aujourd'hui aucun accès disque. Cette fonctionnalité lui en donne un, borné :

- `DOCS_VAULT_PATH` est obligatoire pour que le tool s'active. Non défini → le tool refuse,
  avec un message expliquant quoi configurer.
- Tout chemin d'écriture est construit puis `resolve()` et vérifié `is_relative_to(vault_root)`.
  `resolve()` suivant les liens symboliques, un lien sortant du vault est détecté par cette
  vérification.
- Le paramètre `destination` est refusé s'il est absolu ou s'il contient `..`.
- Chaque segment de chemin passe par l'assainissement, ce qui exclut `/` et les séquences de
  remontée issues d'un titre de document.
- Aucune suppression de fichier : le tool crée, met à jour, déplace et supprime des dossiers
  vides. Les orphelins sont signalés, jamais effacés.
- Les règles ANSSI existantes du projet s'appliquent : ni cookie ni token dans les messages
  d'erreur ou les rapports.

## Surface MCP

```python
docs_sync_tree(
    document: str,                # URL complète ou UUID
    destination: str = "Docs",    # dossier parent, relatif au vault
    dry_run: bool = False,
) -> str                          # rapport JSON
```

`destination` est le dossier **parent** : l'arbre est écrit dans
`<vault>/<destination>/<nom de la racine>/`.

Annotations : `readOnlyHint=False`, `destructiveHint=False`, `idempotentHint=True`,
`openWorldHint=True`. Non destructif car aucune donnée n'est supprimée ; idempotent car deux
exécutions consécutives sans changement amont produisent le même état.

Rapport :

```json
{
  "root": "🐙 LaSuite - Équipe Hub",
  "destination": "Docs/🐙 LaSuite - Équipe Hub",
  "dry_run": false,
  "scanned": 129,
  "created": 0, "updated": 2, "moved": 1, "unchanged": 126,
  "changes": [
    {"action": "updated", "title": "🕸️ Réunions", "path": "Docs/…/🕸️ Réunions/🕸️ Réunions.md"},
    {"action": "moved", "title": "📆 Roadmap 2026", "path": "Docs/…/📆 Roadmap 2026/📆 Roadmap 2026.md",
     "from": "Docs/…/📆 Roadmap 2026.md"}
  ],
  "orphans": [
    {"title": "Ancien doc", "path": "Docs/…/Ancien doc.md"}
  ],
  "errors": []
}
```

Un renommage est un déplacement : l'action est `moved` et l'entrée porte un champ `from`.

`changes` est plafonné à 50 entrées, avec un champ `changes_truncated` quand le plafond est
atteint : le rapport est lu par un LLM, il doit rester compact. `unchanged` n'est qu'un
compteur, jamais une liste. Les orphelins sont toujours listés en entier — c'est ce sur quoi
Louis doit décider.

Un document dont le téléchargement échoue n'interrompt pas la synchronisation : l'erreur est
collectée dans `errors` et les autres documents continuent.

## Découpage du code

| Fichier | Responsabilité |
|---------|----------------|
| `src/mcp_docs/sync.py` | Moteur : découverte, disposition, classement, écriture. Aucune dépendance à MCP. |
| `src/mcp_docs/vault.py` | Système de fichiers : assainissement, frontmatter, écriture atomique, index, garde-fou de chemin. |
| `src/mcp_docs/tools_sync.py` | Tool MCP, validation des entrées, mise en forme du rapport. |
| `src/mcp_docs/client.py` | Ajout : pagination complète des enfants. |
| `src/mcp_docs/models.py` | Ajout : `numchild`, `path`, `depth` sur `DocumentSummary`. |
| `src/mcp_docs/config.py` | Ajout : `vault_path`. |

Le moteur ne connaît ni MCP ni FastMCP : il prend un `DocsClient` et un chemin, et renvoie un
objet de rapport. C'est ce qui permettra d'ajouter un CLI plus tard sans rien déplacer.

## Tests

Mocks `respx` pour l'API, `tmp_path` pour le vault, jamais d'appel réseau réel.

Moteur et disposition :
- création d'un arbre complet sur un vault vide
- deuxième passage sans changement amont : zéro requête de contenu, zéro écriture
- un document modifié : lui seul est téléchargé et réécrit
- feuille devenant parent : `X.md` → `X/X.md`, pas de doublon créé
- document reparenté : fichier déplacé, `docs_id` préservé
- titre modifié : fichier renommé, signalé dans le rapport
- orphelin : signalé, fichier intact

Vault :
- assainissement de chaque classe de caractère, titre vide, titre trop long
- collision entre frères, et stabilité de la résolution sur deux exécutions
- frontmatter : les clés non-`docs_` de l'utilisateur survivent à une mise à jour
- fichier `.md` sans `docs_id` : jamais lu comme un document synchronisé, jamais écrasé
- `destination` absolue ou contenant `..` : refusée
- lien symbolique sortant du vault : refusé

Tool :
- `DOCS_VAULT_PATH` absent : message d'erreur actionnable, aucune écriture
- `dry_run=True` : rapport complet, vault inchangé, aucun contenu téléchargé
- erreur API sur un document : collectée dans `errors`, les autres aboutissent

Réécriture des liens :
- lien vers un document de l'arbre, avec et sans texte distinct
- lien vers un document hors de l'arbre : intact
- URL `/media/` : intacte

## Hors périmètre, et pourquoi

**Sens vault → Docs.** Implique l'aller-retour Yjs (qui passe par un document temporaire, cf.
`_markdown_to_yjs_base64`) et une vraie gestion de conflits. C'est un second chantier.

**Images et pièces jointes.** Décision explicite de Louis : le vault est une sauvegarde
textuelle, pas de code dédié.

**Merge des modifications locales.** Le vault n'étant jamais source de vérité, un document
dont la date amont a bougé est réécrit sans condition. Conséquence assumée : une annotation
locale sur un fichier synchronisé est écrasée à la prochaine synchronisation de ce document.
Le vault étant un dépôt git, elle reste récupérable dans l'historique.

**CLI et job planifié.** Louis ne passe pas par le terminal ; la routine sera une skill
appelant le tool MCP. Le moteur est isolé de MCP pour qu'un CLI reste trivial à ajouter.

**Suppression des orphelins.** Signalés seulement, en v1. Une synchronisation qui supprime des
fichiers doit avoir fait ses preuves avant qu'on lui en donne le droit.
