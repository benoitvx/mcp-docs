# CLAUDE.md — MCP Server Docs (La Suite numérique)

# Project Instructions

## Context

**mcp-docs** est un serveur MCP (Model Context Protocol) qui expose l'API de [Docs](https://docs.numerique.gouv.fr/) (La Suite numérique) aux agents IA.

Il permet à un LLM (Assistant IA, Claude, etc.) d'interagir avec les documents Docs : lister, lire (en Markdown), créer, et à terme mettre à jour des documents.

Cas d'usage prioritaires :
- **Docs → Obsidian** : récupérer le contenu d'un document en Markdown
- **Obsidian → Docs** : pousser un fichier Markdown comme nouveau document
- **Agent IA** : permettre à l'Assistant IA d'accéder aux documents de l'utilisateur

Ce projet fait partie de la **Data Platform** (brique données & MCP du socle IA interministériel, département IAE de la DINUM).

Repo Docs upstream : https://github.com/suitenumerique/docs

## Language

| Context | Language |
|---------|----------|
| Source code (variables, functions, types) | English |
| Code comments | English |
| Commit messages | **English** (La Suite convention, gitmoji) |
| Issues, PR, discussions | **French** |
| Documentation | French |

---

## API Docs — Référence

### Base URLs

- **API interne** (auth par cookie session) : `https://docs.numerique.gouv.fr/api/v1.0/`
- **API externe** (auth OIDC resource server) : `https://docs.numerique.gouv.fr/external_api/v1.0/` — **activée en prod** (confirmé avril 2026, issue #1703)

### Authentification

**Actuellement (POC)** : cookie de session (`docs_sessionid`) récupéré après login ProConnect. Les requêtes POST nécessitent un token CSRF généré côté client (cookie `csrftoken` de 64 chars + header `X-CSRFToken` + header `Referer`).

**Cible** : OIDC Resource Server via `django-lasuite` sur `/external_api/v1.0/`. L'app doit s'authentifier via ProConnect (Bearer token OIDC). Token exchange à venir. Variables d'environnement côté serveur Docs :
```
OIDC_RESOURCE_SERVER_ENABLED=True
OIDC_OP_URL=
OIDC_OP_INTROSPECTION_ENDPOINT=
OIDC_RS_CLIENT_ID=
OIDC_RS_CLIENT_SECRET=
```

Doc : https://github.com/suitenumerique/django-lasuite/blob/main/documentation/how-to-use-oidc-resource-server-backend.md

### Endpoints utilisés

#### Lister les documents
```
GET /api/v1.0/documents/?page_size=20&ordering=-updated_at
```
Réponse paginée : `count`, `results[]` avec `id`, `title`, `created_at`, `updated_at`.

Filtres utiles : `?title=`, `?q=` (recherche), `?is_creator_me=true`.

#### Récupérer le contenu d'un document
```
GET /api/v1.0/documents/{id}/content/?content_format=markdown
```
Formats supportés : `markdown`, `html`, `json`.

Réponse :
```json
{
  "id": "uuid",
  "title": "Titre du document",
  "content": "# Contenu en markdown...",
  "created_at": "...",
  "updated_at": "..."
}
```

#### Créer un document depuis un fichier Markdown
```
POST /api/v1.0/documents/
Content-Type: multipart/form-data

file: <fichier.md>
title: "Titre du document" (optionnel, sinon nom du fichier)
```
Le backend convertit automatiquement le Markdown en format interne (Yjs).

Réponse : `201 Created` avec `id`, `title`.

#### Récupérer les infos utilisateur
```
GET /api/v1.0/users/me/
```

### Endpoints non disponibles (à suivre)

- `PUT /api/v1.0/documents/{id}/` — mise à jour du contenu (ne supporte pas l'envoi de Markdown, attend du Yjs base64)
- `DELETE /api/v1.0/documents/{id}/` — suppression

### Prochaines étapes

- **Migrer vers l'API externe** (`/external_api/v1.0/`) avec auth OIDC Bearer token via ProConnect (PR #1923, issue #1703)
- **Implémenter `docs_list_children`** (P2)
- **Token exchange** — à venir côté La Suite (@jmaupetit)

---

## Architecture

```
mcp-docs/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .pre-commit-config.yaml  # gitleaks
├── .github/
│   ├── workflows/ci.yml     # CI (lint, typecheck, tests, audit, secrets scan)
│   └── dependabot.yml       # Mises à jour auto des deps
├── audits/                  # Rapports d'audit sécurité ANSSI
├── src/
│   └── mcp_docs/
│       ├── __init__.py
│       ├── app.py           # Instance FastMCP + lifespan (évite imports circulaires)
│       ├── server.py        # Entry point main()
│       ├── client.py        # Client HTTP pour l'API Docs (DocsClient)
│       └── tools.py         # Définition des tools MCP
└── tests/
    ├── conftest.py          # Fixtures + respx mocks
    ├── test_client.py       # Tests unitaires client HTTP
    └── test_tools.py        # Tests des tools MCP
```

---

## Stack

| Component | Choix |
|-----------|-------|
| Language | Python 3.12+ |
| MCP SDK | `mcp` (pip install mcp) |
| HTTP client | `httpx` |
| Package manager | `uv` |
| Tests | pytest |
| Formatting | ruff |
| Type checking | pyright |

### MCP SDK — Patterns

Le serveur MCP utilise le SDK Python officiel :

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("docs")

@mcp.tool()
async def list_documents(page_size: int = 20) -> str:
    """Liste les documents Docs de l'utilisateur."""
    ...

@mcp.tool()
async def get_document_content(document_id: str, format: str = "markdown") -> str:
    """Récupère le contenu d'un document en Markdown, HTML ou JSON."""
    ...

@mcp.tool()
async def create_document(title: str, markdown_content: str) -> str:
    """Crée un nouveau document dans Docs à partir de contenu Markdown."""
    ...
```

Doc MCP SDK : https://modelcontextprotocol.io/

### Tools MCP

| Tool | Description | Priorité | Statut |
|------|-------------|----------|--------|
| `docs_list_documents` | Lister les documents (paginé, filtrable) | P0 | ✅ |
| `docs_get_document_content` | Récupérer le contenu en markdown/html/json | P0 | ✅ |
| `docs_create_document` | Créer un document depuis du Markdown | P0 | ✅ |
| `docs_search_documents` | Rechercher par titre ou contenu | P1 | ✅ |
| `docs_get_me` | Infos de l'utilisateur connecté | P1 | ✅ |
| `docs_list_children` | Lister les sous-documents | P2 | ❌ |

---

## Expected Behavior

### Plan Mode

Pour toute tâche non triviale (3+ étapes ou décision d'architecture) :

1. Écrire le plan dans `tasks/todo.md` avec des items cochables
2. Valider le plan avant d'implémenter
3. Cocher les items au fur et à mesure
4. Ajouter une section "résultat" à la fin

### Bug Fixing

Face à un bug : le corriger directement. Pointer les logs, erreurs et tests en échec — puis résoudre.

### Code Quality

Pour tout changement non trivial : **"Existe-t-il une solution plus élégante ?"**

---

## Security — ANSSI

Ref: https://cyber.gouv.fr/les-regles-de-securite

- [ ] Aucun secret, clé API ou mot de passe dans le code
- [ ] Variables d'environnement non committées, différentes par environnement
- [ ] Validation de toutes les entrées
- [ ] Messages d'erreur sans détails internes
- [ ] Dépendances à jour
- [ ] Pas de `print()` de données sensibles (tokens, cookies)

Le cookie de session et les tokens OIDC sont des **données sensibles** — ne jamais les logger, les inclure dans les messages d'erreur, ou les stocker en clair.

> Pour un audit complet, la skill `securite-anssi` de [etalab-ia/skills](https://github.com/etalab-ia/skills) fournit une checklist 12 règles ANSSI.

---

## Tests

```bash
uv run pytest              # Tests unitaires
uv run pytest --cov        # Couverture
uv run ruff check .        # Lint
uv run pyright             # Type check
```

Mocker les appels HTTP à l'API Docs avec `httpx`/`respx` dans les tests — ne jamais appeler l'API réelle dans les tests.

---

## Git Conventions

### Commits (gitmoji)

Format : `<emoji>(<scope>) <subject>`

```
✨(tools) add get_document_content tool
🐛(client) fix auth header for session cookie
♻️(server) refactor tool registration
📝(readme) document installation and config
```

### Branches

```
feat/description-courte
fix/description-courte
```

---

## Configuration

Variables d'environnement :

```bash
# URL de base de l'API Docs
DOCS_BASE_URL=https://docs.numerique.gouv.fr

# Auth mode: "session" (cookie) ou "oidc" (resource server)
DOCS_AUTH_MODE=session

# Pour auth session (POC)
DOCS_SESSION_COOKIE=<docs_sessionid value>

# Pour auth OIDC (cible)
DOCS_OIDC_TOKEN=<bearer token>
```

---

## Relevant Skills

### mcp-builder ([anthropics/skills](https://github.com/anthropics/skills))

Guide de développement de serveurs MCP. Utiliser cette skill :

- **Avant d'implémenter un nouveau tool MCP** — pour vérifier les bonnes pratiques (nommage, annotations, input validation Pydantic, error handling, pagination)
- **En phase de review** — pour auditer la qualité des tools existants (checklist Python dans `reference/python_mcp_server.md`)
- **Pour créer des évaluations** — quand on veut tester que le serveur MCP permet à un LLM de répondre à des questions réalistes (`reference/evaluation.md`)

### Autres skills ([etalab-ia/skills](https://github.com/etalab-ia/skills))

- **securite-anssi** — Audit sécurité ANSSI 12 règles. Utiliser avant tout déploiement ou pour valider les pratiques auth/secrets.
- **datagouv-apis** — Référence APIs data.gouv.fr (si intégration future avec les données ouvertes)
