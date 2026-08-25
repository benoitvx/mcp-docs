# Tâche — Réparer la CI (branche `fix/ci-green`)

## Contexte

Les 3 PR ouvertes (#8, #9, #10) sont rouges sur les mêmes deux jobs, pour des causes
systémiques indépendantes du code proposé :

1. `secrets-scan` : `gitleaks-action@v2` reçoit un `403 Resource not accessible by
   integration` sur `GET /repos/.../pulls/{n}/commits` — le `GITHUB_TOKEN` par défaut
   n'a pas `pull-requests: read`, et aucun bloc `permissions:` n'est déclaré.
2. `lint-test` : `ruff`, `pyright` et `pytest` passent ; seul `pip-audit` échoue
   (30 CVE / 8 paquets runtime : starlette, cryptography, mcp, pyjwt,
   python-multipart, idna, click, pydantic-settings).

## Plan

- [x] Déclarer `permissions:` explicitement sur les deux jobs du workflow
- [x] `uv lock --upgrade` pour purger les CVE runtime
- [x] Vérifier localement : `pip-audit` propre
- [x] Vérifier localement : `ruff` + `pyright` + `pytest` verts après le bump
- [x] Commit ciblé (workflow + uv.lock uniquement, pas le WIP en cours)
- [x] Pousser et ouvrir la PR

## Résultat

**`secrets-scan`** — ajout d'un `permissions: {}` global (moindre privilège) et d'un bloc
explicite par job. `secrets-scan` obtient `pull-requests: read`, ce qui débloque l'appel
`/pulls/{n}/commits` de gitleaks. `lint-test` se contente de `contents: read`.

**`lint-test` / `pip-audit`** — `uv lock --upgrade` : 30 CVE sur 8 paquets ramenées à 0.
Bumps notables : `mcp` 1.27.0 → 1.29.1, `starlette` 1.0.0 → 1.6.0,
`cryptography` 46.0.7 → 50.0.0, `pyjwt` 2.12.1 → 2.13.0,
`python-multipart` 0.0.26 → 0.0.32, `idna` 3.11 → 3.19, `click` 8.3.2 → 8.4.2,
`pydantic-settings` 2.14.0 → 2.15.0.

Les planchers de `pyproject.toml` ont été remontés sur les advisories (`mcp>=1.28.1`,
`pydantic-settings>=2.14.2`, `python-multipart>=0.0.31`) : le lock protège la CI, mais
une résolution fraîche depuis le seul `pyproject.toml` pouvait encore retomber sur une
version vulnérable.

`mcp` est **plafonné sous 2.0**. `uv lock --upgrade` sans contrainte proposait `mcp 2.1.0` ;
la 1.28.1 suffit à purger les advisories, et valider un saut de version majeure n'a pas sa
place dans un correctif de sécurité. À traiter séparément.

**Vérifications locales** : `ruff` ✅, `pyright` (0 erreur) ✅, `pytest` (180 tests) ✅.
`pip-audit` ne tourne pas sur cette machine (`ensurepip` crashe en SIGABRT à la création de
son venv isolé — problème local, la CI Linux n'est pas concernée) ; les 32 paquets runtime
épinglés ont donc été vérifiés directement contre l'API OSV : **0 vulnérabilité**.

**Reste à faire** : migration `mcp` 2.x, dans une PR dédiée.
