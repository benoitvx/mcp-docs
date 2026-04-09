# mcp-docs

Serveur MCP (Model Context Protocol) pour l'API [Docs](https://docs.numerique.gouv.fr/) de La Suite numérique.

Permet à un agent IA d'interagir avec les documents Docs : lister, lire (Markdown), créer.

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone <repo-url>
cd mcp-docs
uv sync
```

## Configuration

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DOCS_BASE_URL` | URL de base de l'API Docs | `https://docs.numerique.gouv.fr` |
| `DOCS_AUTH_MODE` | Mode d'authentification : `session` ou `oidc` | `session` |
| `DOCS_SESSION_COOKIE` | Valeur du cookie `sessionid` (mode session) | — |
| `DOCS_OIDC_TOKEN` | Bearer token OIDC (mode oidc) | — |

### Récupérer le cookie de session

1. Se connecter à https://docs.numerique.gouv.fr via ProConnect
2. Ouvrir les DevTools du navigateur (F12) → onglet Application → Cookies
3. Copier la valeur du cookie `docs_sessionid`

## Lancement

```bash
# Directement
uv run mcp-docs

# Ou via le script installé
uv run --directory /chemin/vers/mcp-docs mcp-docs
```

## Configuration Claude Desktop

Ajouter dans `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "docs": {
      "command": "uv",
      "args": ["run", "--directory", "/chemin/vers/mcp-docs", "mcp-docs"],
      "env": {
        "DOCS_BASE_URL": "https://docs.numerique.gouv.fr",
        "DOCS_AUTH_MODE": "session",
        "DOCS_SESSION_COOKIE": "<votre-cookie-sessionid>"
      }
    }
  }
}
```

## Tools MCP disponibles

| Tool | Description |
|------|-------------|
| `docs_list_documents` | Lister les documents (paginé) |
| `docs_get_document_content` | Récupérer le contenu en markdown/html/json |
| `docs_create_document` | Créer un document depuis du Markdown |
| `docs_search_documents` | Rechercher par titre ou contenu |
| `docs_get_me` | Infos de l'utilisateur connecté |

## Sécurité

### Rotation des secrets

Le cookie de session `docs_sessionid` a une durée de vie limitée (expiration ProConnect). En cas de doute sur une compromission :

1. **Révoquer la session** : se déconnecter de https://docs.numerique.gouv.fr (invalide le cookie côté serveur)
2. **Supprimer le cookie** des variables d'environnement (`~/.claude.json`, `.mcp.json`, tout fichier de config)
3. **Se reconnecter** via ProConnect pour obtenir un nouveau cookie
4. **Mettre à jour** la config MCP avec le nouveau cookie

Pour le mode OIDC : révoquer le token auprès du fournisseur d'identité et en regénérer un.

### Scan de secrets

Un pre-commit hook `gitleaks` empêche de committer des secrets accidentellement :

```bash
# Installation
uv run pre-commit install
```

### Signalement d'incident

En cas d'incident de sécurité (fuite de secret, accès non autorisé) :
- Révoquer immédiatement les accès compromis (étapes ci-dessus)
- Contacter le CERT ministériel (DINUM)
- Documenter l'incident (date, périmètre, actions prises)

## Développement

```bash
uv run pytest              # Tests
uv run pytest --cov        # Tests + couverture
uv run ruff check .        # Lint
uv run pyright             # Type check
```
