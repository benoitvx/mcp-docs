# Livré — Garde anti-imbrication de `docs_sync_tree` (2026-08-24)

**Problème :** une destination pointant dans le dossier d'un autre Docs laissait l'arbre
s'installer entre ce document et ses enfants, sans erreur. Détecté seulement à la sync
suivante du vrai parent, sous forme d'orphelins.

- [x] `_folder_owner` / `_nesting_owner` dans `sync.py` — détection par convention
      folder-note (`X/X.md` porteur d'un `docs_id`), remontée de toute la chaîne d'ancêtres.
- [x] Refus des placements **nouveaux** uniquement (`target != current`) : une note qui vit
      déjà dans le dossier de son parent continue d'être mise à jour sur place.
- [x] Erreur `nested_in_document` avec `owner_document_id` dans le rapport.
- [x] 5 tests (`test_sync_engine.py`) — refus, nommage du propriétaire, ancêtre profond,
      non-régression sur la mise à jour en place, dossier d'organisation non confondu.
- [x] Docstring `docs_sync_tree` + section « Choisir la destination d'une sync » dans
      `CLAUDE.md` (lecture du vault à la demande, pas de fichier sommaire à maintenir).
- [x] `uv run pytest` (272 passed), `uv run ruff check .` — OK. `pyright` : 1 erreur
      pré-existante dans `session_refresh.py:114`, sans rapport (vérifiée sur la base stashée).

**Écarté :** mode squelette pour `docs_sync_tree` — sans objet, voir `lessons.md`.

---

# Todo (en attente) — Pagination de docs_get_document_content

**Goal:** permettre de lire un gros document Docs sans faire exploser le contexte d'une
conversation. Aujourd'hui `docs_get_document_content` renvoie tout le contenu en un seul
tool result — un doc de 54k-88k caractères force soit un dépassement de la limite de tokens
du tool result, soit un contournement bricolé (chunking Grep, observé dans une autre conv).

**Contrainte découverte :** l'API Docs (`/formatted-content/`) ne propose aucune pagination
côté serveur — elle renvoie toujours le document entier en un seul appel HTTP. La pagination
doit donc se faire côté `mcp-docs` : fetcher le contenu complet (un seul appel, pas cher),
puis ne renvoyer à l'agent qu'une tranche bornée avec un curseur pour lire la suite.

**Ce qui reste hors scope :**
- Mode squelette pour `docs_sync_tree` (voir plan précédent, commit `984bc14`) — sans lien
  avec ce sujet : `docs_sync_tree` ne renvoie déjà jamais de contenu à l'agent (écriture
  directe sur disque), donc les gros documents n'y posent pas de problème de tokens.
- Pagination de `docs_list_children` — déjà paginé nativement (`page`/`page_size`), pas concerné.

**Architecture:** `docs_get_document_content` gagne deux paramètres, `offset: int = 0` et
`max_chars: int = <à trancher, voir décision D1>`. Le contenu déjà récupéré est tranché en
Python (indexation par code point, sûre en UTF-8) avant d'être renvoyé, avec une note de
pagination si tronqué (offset suivant, taille totale).

**Tech Stack:** Python 3.12, aucun changement de dépendance.

## Global Constraints

- Code, noms et commentaires en anglais ; messages de commit en anglais (gitmoji) ; docs en français.
- `ruff` line-length 120. `pyright` en mode `standard`.
- Rétrocompatible : un appel sans `offset`/`max_chars` sur un document sous le seuil doit
  renvoyer exactement ce qu'il renvoie aujourd'hui (aucun test existant ne doit casser).

---

## Décision D1 — valeur par défaut de `max_chars`

**Tranché : 20 000 caractères** (option conservatrice). Borne le coût token par appel de
façon nette et prévisible, quitte à couper en plusieurs appels des documents de taille
moyenne qui passaient jusqu'ici en un seul.

---

## Task 1: Pagination dans `docs_get_document_content`

**Files:**
- Modify: `src/mcp_docs/tools.py` (fonction `docs_get_document_content`)
- Test: `tests/test_tools.py`

- [ ] Ajouter les paramètres `offset: int = 0` et `max_chars: int = 20000` à la signature.
- [ ] Valider `offset >= 0` et `max_chars > 0`, sinon `"Error: ..."` (cohérent avec le style
  de validation existant du fichier).
- [ ] Écrire un helper `_paginate(content: str, offset: int, max_chars: int) -> tuple[str, dict]`
  dans `tools.py` (pas dans `client.py` — c'est une préoccupation de présentation à l'agent,
  pas de récupération de données) :
  - Tranche `content[offset:offset + max_chars]` (indexation par code point — sûr en UTF-8,
    Python n'indexe jamais au milieu d'un caractère).
  - Retourne un dict `{"offset": offset, "returned_chars": N, "total_chars": M,
    "truncated": bool, "next_offset": offset + N si truncated sinon None}`.
- [ ] Branche `markdown` : si `truncated`, ajouter en pied de réponse :
  `\n\n---\n[Truncated: {returned_chars} of {total_chars} chars shown. Call again with
  offset={next_offset} to continue.]`
- [ ] Branche `html` : même traitement (contenu tranché + note de troncature en commentaire
  HTML `<!-- Truncated: ... -->`), plutôt que le `model_dump_json()` actuel qui dumperait le
  contenu complet non tranché.
- [ ] Branche `json` : construire le dict de sortie à la main (pas `model_dump_json()`) avec
  `content` tranché et un sous-objet `"pagination": {...}` — pas de champ de pagination
  implicite mélangé aux champs du document.
- [ ] Mettre à jour le docstring : documenter `offset`/`max_chars` et le format de la note
  de troncature.

---

## Task 2: Tests

**Files:** `tests/test_tools.py`

- [ ] `test_short_content_is_returned_whole_without_pagination_note` — contenu sous le seuil,
  aucune note de troncature, comportement identique à avant (garantit la non-régression).
- [ ] `test_long_content_is_truncated_at_max_chars_with_a_continuation_note` (markdown).
- [ ] `test_offset_resumes_from_the_right_position` — deuxième appel avec `next_offset` de
  la réponse précédente reconstitue le contenu complet une fois concaténé.
- [ ] `test_html_format_truncates_and_notes_it`.
- [ ] `test_json_format_returns_pagination_metadata`.
- [ ] `test_rejects_negative_offset`.
- [ ] `test_rejects_non_positive_max_chars`.
- [ ] `test_offset_past_end_of_content_returns_empty_not_truncated` — cas limite, ne doit pas
  planter ni marquer `truncated: true` avec `next_offset` invalide.

---

## Task 3: Documentation

**Files:** `README.md`, `CLAUDE.md`

- [ ] `README.md` — note sous le tableau des tools de lecture : `docs_get_document_content`
  pagine désormais les gros documents (`offset`/`max_chars`), au lieu de forcer un chunking
  manuel côté agent.
- [ ] `CLAUDE.md` — section "API Docs — Référence" : documenter que `/formatted-content/`
  n'a pas de pagination serveur, et que `mcp-docs` pagine côté client pour cette raison
  (context utile pour la prochaine session qui touchera ce endpoint).

---

## Task 4: Vérification

- [ ] `uv run pytest`
- [ ] `uv run ruff check .`
- [ ] `uv run pyright`

---

## Out of scope (rappel)

- Mode squelette `docs_sync_tree` — sans rapport, ce tool n'a pas ce problème.
- Pagination de `docs_list_children` — déjà paginé.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 1 décision (D1, tranchée : 20 000 car.), 1 remarque mineure acceptée (dérive possible du dict `json` manuel) |
| Outside Voice | — | Second avis inter-modèle | 0 (sciemment sauté) | — | Même raison qu'au run précédent — changement contenu, pas architecture, projet solo |

**VERDICT:** ENG CLEARED — prêt à implémenter.

NO UNRESOLVED DECISIONS
