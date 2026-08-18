# Todo — Garde-fou anti-crawl-manuel pour les tools de lecture Docs

**Goal:** empêcher un agent d'utiliser `docs_list_children` + `docs_get_document_content` +
`Write` pour reconstruire à la main un arbre de documents dans un vault, alors que
`docs_sync_tree` existe déjà et fait ce travail en beaucoup moins de tokens (découverte
parallèle par niveaux, écriture directe sur disque côté serveur MCP, incrémental sur
`updated_at`).

**Contexte / preuve du problème:** dans une autre conversation, un agent a mirroré un arbre
de 49 documents à la main : `docs_list_children` nœud par nœud (~40 appels), `docs_get_document_content`
sur des pages de 54k-88k caractères (dépassant la limite de tokens du tool result, contourné
par du chunking Grep), puis recopie de dizaines de milliers de caractères en clair dans les
paramètres `Write`. Aucune de ces étapes ne passe par `docs_sync_tree`.

**Ce qui est hors scope (décidé avec l'utilisateur):**
- Mode "squelette" (métadonnées seules, contenu différé) pour `docs_sync_tree` — l'utilisateur
  fait le premier sync à la main sans problème ; le vrai besoin (syncs récurrents automatisés)
  n'est pas encore implémenté et sort du cadre de cette tâche.
- Pagination/chunking natif de `docs_get_document_content` pour les documents volumineux —
  non demandé explicitement par l'utilisateur dans cet échange, à reprendre séparément si besoin.

**Architecture:** aucun changement de comportement, uniquement les docstrings exposées aux
agents comme description de tool (visibles dans le prompt système MCP), plus la doc humaine
(README, CLAUDE.md) pour cohérence.

**Tech Stack:** Python 3.12, aucun changement de dépendance.

## Global Constraints

- Code, noms et commentaires en anglais ; messages de commit en anglais (gitmoji) ; docs en français.
- `ruff` line-length 120. `pyright` en mode `standard`.
- Aucun changement de comportement — uniquement des docstrings/documentation.

---

## Task 1: Docstring de `docs_list_children` — rediriger vers `docs_sync_tree`

**Files:**
- Modify: `src/mcp_docs/tools.py` (fonction `docs_list_children`, ~ligne 298-310)

- [x] Ajouter au docstring, après la première ligne de résumé :

```
    For mirroring an entire document tree to disk (e.g. an Obsidian vault), do not
    call this tool once per node to walk the tree by hand — use `docs_sync_tree`
    instead. It discovers every level in parallel and writes directly to the vault,
    which is both faster and far cheaper in tokens than reconstructing the tree
    node by node with this tool.
```

- [x] Vérifier qu'aucun test n'assert sur le texte exact du docstring (`grep -n "docs_list_children" tests/`).

---

## Task 2: Docstring de `docs_get_document_content` — même redirection

**Files:**
- Modify: `src/mcp_docs/tools.py` (fonction `docs_get_document_content`, ~ligne 80-90)

- [x] Ajouter au docstring :

```
    For mirroring an entire document tree to disk (e.g. an Obsidian vault), do not
    call this tool once per document and copy the result into `Write` — use
    `docs_sync_tree` instead. It fetches content and writes it directly server-side,
    skipping documents that have not changed. Reconstructing a tree this way costs
    far more tokens and hits this tool's own size limits on large documents.
```

- [x] Vérifier qu'aucun test n'assert sur le texte exact du docstring.

---

## Task 3: Docstring de `docs_sync_tree` — pointeur réciproque

**Files:**
- Modify: `src/mcp_docs/tools_sync.py` (fonction `docs_sync_tree`, ~ligne 60-76)

- [x] Ajouter une phrase en tête du docstring (avant "Args:") indiquant que c'est le chemin
  recommandé pour toute réplication d'arbre, en écho aux deux redirections ci-dessus :

```
    This is the preferred way to mirror a tree: prefer it over calling
    `docs_list_children` and `docs_get_document_content` once per document.
```

---

## Task 4: Cohérence doc humaine

**Files:**
- Modify: `CLAUDE.md` (table "Tools MCP")
- Modify: `README.md` (si une section liste les tools ou leur usage recommandé — vérifier d'abord)

- [x] Dans `CLAUDE.md`, table des tools MCP : ajouter une note sous le tableau précisant que
  `docs_sync_tree` est le chemin recommandé pour toute réplication d'arbre, les autres tools
  de lecture étant pour un usage ponctuel document-par-document.
- [x] Vérifier `README.md` avec `grep -n "docs_list_children\|docs_sync_tree" README.md` avant
  de décider s'il y a quelque chose à ajouter.

---

## Task 5: Vérification

- [x] `uv run pytest` — 267 passed, aucune régression.
- [x] `uv run ruff check .` — All checks passed.
- [x] `uv run pyright` — 1 erreur préexistante (`session_refresh.py:114`), sans rapport
  avec ce changement (déjà notée dans le "Reste à faire" du plan `docs_sync_tree`).
- [x] Docstrings modifiées : chacune reste sous 6 lignes ajoutées.

## Résultat

Livré le 2026-08-18. Docstrings de `docs_get_document_content`, `docs_list_children` et
`docs_sync_tree` mises à jour pour rediriger vers `docs_sync_tree` sur toute réplication
d'arbre. README.md et CLAUDE.md alignés. Aucun changement de comportement, 267 tests verts.

---

## Out of scope (rappel)

- Mode squelette pour `docs_sync_tree` (voir ci-dessus).
- Pagination de `docs_get_document_content`.
- Toute automatisation de sync récurrente (pas encore implémentée dans ce projet).

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 0 issues, texte seul, aucun nouveau chemin d'exécution |
| Outside Voice | — | Second avis inter-modèle | 0 (sciemment sauté) | — | Disproportionné pour un changement de 3 docstrings sur projet solo — codex non installé, sous-agent jugé inutile ici |

**VERDICT:** ENG CLEARED — texte seul, zéro régression possible, prêt à implémenter.

NO UNRESOLVED DECISIONS
