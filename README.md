# mcp-docs

Serveur **MCP (Model Context Protocol)** pour l'API [Docs](https://docs.numerique.gouv.fr/) de La Suite numérique.

Il expose **25 tools** et 2 resources permettant à un agent IA d'interagir avec les documents Docs : lire, créer, mettre à jour le contenu (markdown), gérer les accès et les invitations, organiser l'arborescence, utiliser les fonctions IA natives de Docs (résumé, correction, traduction), et plus encore.

---

## Table des matières

- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation avec Claude Desktop](#utilisation-avec-claude-desktop)
- [Tools disponibles](#tools-disponibles)
- [Exemples de workflows](#exemples-de-workflows)
- [Validation de la configuration](#validation-de-la-configuration)
- [Sécurité](#sécurité)
- [Développement](#développement)
- [Architecture](#architecture)

---

## Prérequis

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/) (gestionnaire de paquets Python)
- Un compte sur une instance Docs (ex. https://docs.numerique.gouv.fr)

---

## Installation

```bash
git clone <repo-url>
cd mcp-docs
uv sync
```

---

## Configuration

Le serveur est configuré par variables d'environnement, préfixées `DOCS_`.

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DOCS_BASE_URL` | URL de base de l'API Docs | `https://docs.numerique.gouv.fr` |
| `DOCS_AUTH_MODE` | `session` (cookie) ou `oidc` (Bearer token) | `session` |
| `DOCS_SESSION_COOKIE` | Cookie `docs_sessionid` (mode session, explicite) | — |
| `DOCS_SESSION_FILE` | Chemin JSON contenant le cookie (mode session, alternative) | `$XDG_STATE_HOME/mcp-docs/session.json` |
| `DOCS_OIDC_TOKEN` | Bearer token OIDC (mode oidc) | — |
| `DOCS_MAX_RETRIES` | Nombre de retries sur erreurs transitoires | `3` |
| `DOCS_MAX_CONCURRENT` | Limite de requêtes concurrentes | `5` |

### Récupérer le cookie de session

Le mode `session` est le mode par défaut. Il utilise le cookie `docs_sessionid` obtenu après connexion ProConnect. Deux options :

#### Option A — Automatique via Playwright (recommandé)

Un CLI dédié lance un navigateur, attend que vous complétiez la connexion ProConnect, puis écrit le cookie dans un fichier local lu automatiquement par le MCP :

```bash
# Installation (une seule fois)
uv sync --extra browser
uv run playwright install chromium

# Rafraîchir le cookie (aucun argument requis)
uv run mcp-docs-refresh-session
```

Au premier lancement, un Chromium s'ouvre — terminez la connexion ProConnect dans la fenêtre. Le cookie est écrit dans `~/.local/state/mcp-docs/session.json` (permissions `0600`) et le MCP le lit au démarrage.

Les lancements suivants vérifient d'abord si le cookie existant est encore valide (≈ 200 ms, aucun navigateur lancé). Si oui, on sort immédiatement. Sinon, le flow Playwright redémarre — et comme un profil navigateur persistant est conservé sous `~/.local/share/mcp-docs/browser-profile/`, la session ProConnect est souvent déjà connue, donc la récupération est quasi-instantanée.

Override du chemin : `DOCS_SESSION_FILE=/autre/chemin.json uv run mcp-docs-refresh-session`.
Timeout configurable : `uv run mcp-docs-refresh-session --timeout 600`.

#### Rafraîchissement automatique (launchd, macOS)

Pour ne plus jamais avoir à lancer la commande manuellement, planifier un run horaire en arrière-plan avec `launchd`. Le flag `--headless` fait tourner Chromium sans fenêtre ; si la session ProConnect IdP est encore vivante dans le profil persistant, le refresh est invisible. Si elle a expiré, le job échoue et une notification macOS s'affiche pour te signaler qu'il faut relancer en interactif.

Récupérer le chemin absolu de `uv` :

```bash
which uv      # ex: /opt/homebrew/bin/uv
```

Créer `~/Library/LaunchAgents/mcp-docs.refresh.plist` (adapter `PATH_TO_UV` et `PATH_TO_REPO`) :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>mcp-docs.refresh</string>
    <key>ProgramArguments</key>
    <array>
        <string>PATH_TO_UV</string>
        <string>run</string>
        <string>--directory</string>
        <string>PATH_TO_REPO</string>
        <string>mcp-docs-refresh-session</string>
        <string>--headless</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>UV_PROJECT_ENVIRONMENT</key>
        <string>/tmp/venv-mcp-docs</string>
        <key>UV_LINK_MODE</key>
        <string>copy</string>
    </dict>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/mcp-docs-refresh.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/mcp-docs-refresh.err.log</string>
</dict>
</plist>
```

Charger (ou recharger après une modification du plist) :

```bash
launchctl bootout gui/$(id -u)/mcp-docs.refresh 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/mcp-docs.refresh.plist
launchctl kickstart -k gui/$(id -u)/mcp-docs.refresh   # déclenche immédiatement pour tester
```

Vérifier :

```bash
launchctl print gui/$(id -u)/mcp-docs.refresh | head
tail -f /tmp/mcp-docs-refresh.err.log
```

Désactiver :

```bash
launchctl bootout gui/$(id -u)/mcp-docs.refresh
rm ~/Library/LaunchAgents/mcp-docs.refresh.plist
```

#### Option B — Manuel via DevTools

Si vous préférez ne pas installer Playwright :

1. Se connecter à https://docs.numerique.gouv.fr (ou votre instance) via ProConnect
2. Ouvrir les DevTools du navigateur (F12) → onglet **Application** → **Cookies**
3. Copier la valeur du cookie `docs_sessionid` et la placer dans `DOCS_SESSION_COOKIE`

> ⚠️ Ce cookie a une durée de vie limitée. Voir [Sécurité](#sécurité) pour la rotation.

**Précédence** : `DOCS_SESSION_COOKIE` (env) > `DOCS_SESSION_FILE` > chemin par défaut.

### Mode OIDC (cible)

Le mode `oidc` est prévu pour la migration vers `/external_api/v1.0/` avec Bearer token ProConnect. Pas encore opérationnel en production.

---

## Utilisation avec Claude Desktop

Ajouter dans `claude_desktop_config.json` (macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`) :

```json
{
  "mcpServers": {
    "docs": {
      "command": "uv",
      "args": ["run", "--directory", "/chemin/vers/mcp-docs", "mcp-docs"],
      "env": {
        "DOCS_BASE_URL": "https://docs.numerique.gouv.fr",
        "DOCS_AUTH_MODE": "session"
      }
    }
  }
}
```

Le cookie n'apparaît **pas** dans la config — il est lu depuis `~/.local/state/mcp-docs/session.json`, alimenté par `mcp-docs-refresh-session` (voir [Configuration](#configuration)). Si tu préfères malgré tout l'injecter en env, ajoute `"DOCS_SESSION_COOKIE": "..."` (mais tu perds la rotation automatique et le cookie finit écrit dans ce fichier de config).

Redémarrer Claude Desktop. Le serveur expose alors les 25 tools MCP.

---

## Tools disponibles

### 📖 Lecture (7)

| Tool | Description |
|------|-------------|
| `docs_list_documents` | Lister les documents (paginé, trié par date de mise à jour) |
| `docs_get_document_content` | Récupérer le contenu d'un document (markdown/html/json) |
| `docs_search_documents` | Rechercher par titre ou contenu |
| `docs_list_children` | Lister les sous-documents d'un document parent |
| `docs_get_me` | Infos de l'utilisateur connecté |
| `docs_list_accesses` | Lister les utilisateurs ayant accès à un document |
| `docs_list_invitations` | Lister les invitations en attente sur un document |

### ✏️ Création et édition (5)

| Tool | Description |
|------|-------------|
| `docs_create_document` | Créer un document depuis du markdown |
| `docs_update_document_title` | Renommer un document |
| `docs_update_document_content` | Remplacer le contenu d'un document avec du markdown (formatage préservé) |
| `docs_grant_access` | Donner un accès à un utilisateur (par `user_id`) |
| `docs_create_invitation` | Inviter un utilisateur par email |

### 🗑️ Suppression et gestion d'accès destructive (3)

| Tool | Description |
|------|-------------|
| `docs_delete_document` | Supprimer (corbeille) un document |
| `docs_update_access` | Modifier le rôle d'un accès existant |
| `docs_revoke_access` | Retirer un accès |

### 🤖 IA (2)

| Tool | Description |
|------|-------------|
| `docs_ai_transform` | Transformer du texte : `correct`, `rephrase`, `summarize`, `beautify`, `emojify`, `prompt` |
| `docs_ai_translate` | Traduire du texte (code ISO : `en`, `fr`, `es`, `de`, …) |

### 🔗 Partage par lien (1)

| Tool | Description |
|------|-------------|
| `docs_update_link_configuration` | Configurer le partage par lien : `restricted` / `authenticated` / `public` + rôle |

### ⭐ Favoris (3)

| Tool | Description |
|------|-------------|
| `docs_list_favorites` | Lister les documents favoris |
| `docs_add_favorite` | Ajouter un document aux favoris |
| `docs_remove_favorite` | Retirer un document des favoris |

### 📦 Organisation (4)

| Tool | Description |
|------|-------------|
| `docs_move_document` | Déplacer dans la hiérarchie (`first-child`, `last-child`, `left`, `right`, siblings) |
| `docs_duplicate_document` | Dupliquer (avec ou sans sous-documents, avec ou sans permissions) |
| `docs_list_trashbin` | Lister les documents supprimés |
| `docs_restore_document` | Restaurer un document depuis la corbeille |

### 📚 Resources MCP (2)

| URI | Description |
|-----|-------------|
| `docs://user` | Profil de l'utilisateur authentifié |
| `docs://documents` | 10 documents les plus récemment mis à jour |

---

## Exemples de workflows

### Workflow éditorial avec IA

> « Crée un document "Note de synthèse" avec le contenu markdown suivant : [...]. Demande à l'IA un résumé en une phrase, puis remplace le contenu par ce résumé. »

Outils : `docs_create_document` → `docs_get_document_content` → `docs_ai_transform` (action=`summarize`) → `docs_update_document_content`.

### Traduction et partage public

> « Crée un doc avec un message en français, traduis-le en anglais, crée un nouveau doc avec la traduction, et rends-le public en lecture. »

Outils : `docs_create_document` → `docs_ai_translate` → `docs_create_document` → `docs_update_link_configuration` (`public`, `reader`).

### Organisation hiérarchique

> « Crée un projet "ABC" et ses 3 phases. Déplace chaque phase en enfant du projet. »

Outils : `docs_create_document` (×4) → `docs_move_document` (×3, `last-child`).

### Corbeille et restauration

> « Supprime ce doc, vérifie qu'il est dans la corbeille, puis restaure-le. »

Outils : `docs_delete_document` → `docs_list_trashbin` → `docs_restore_document`.

Plus de scénarios : voir `tasks/` dans le repo.

---

## Validation de la configuration

Pour vérifier rapidement que la config est correcte **avant** de lancer le serveur MCP :

```bash
uv run mcp-docs --config-check
```

Sortie attendue :

```
Config OK: base_url=https://docs.numerique.gouv.fr, auth_mode=session
Auth OK: connected as <Votre Nom> (<votre.email@gouv.fr>)
```

En cas d'erreur (cookie expiré, URL incorrecte), le code de sortie est `1` et le message d'erreur est imprimé sur `stderr`.

---

## Sécurité

### Conformité ANSSI

- Aucun secret dans le code. Les cookies et tokens sont chargés depuis l'environnement
- Validation stricte de toutes les entrées (Pydantic + whitelists pour les rôles/positions)
- Messages d'erreur génériques sans détails internes
- Les tokens ne sont jamais loggés
- Scan de secrets via `gitleaks` en pre-commit

### Rotation des secrets

Le cookie `docs_sessionid` a une durée de vie limitée (expiration Django / ProConnect). En mode fichier — recommandé — la rotation est automatique via `mcp-docs-refresh-session` (fast-path s'il est encore valide, sinon Playwright extrait un nouveau cookie du navigateur). Avec le plist launchd ci-dessus, c'est totalement transparent tant que la session ProConnect IdP tient.

En cas de compromission avérée d'un cookie :

1. **Invalider côté serveur** : se déconnecter de https://docs.numerique.gouv.fr depuis le navigateur où le cookie est vivant (logout UI → destruction de la session Django correspondante).
2. **Nuker le profil Playwright** pour forcer une re-saisie ProConnect :
   ```bash
   rm -rf ~/.local/share/mcp-docs/browser-profile
   rm ~/.local/state/mcp-docs/session.json
   ```
3. **Re-générer** : `uv run mcp-docs-refresh-session` (login ProConnect interactif, nouveau cookie écrit).
4. **Nettoyer** : retirer tout `DOCS_SESSION_COOKIE` résiduel de `~/.claude.json`, `.mcp.json`, `claude_desktop_config.json`.

Pour le mode OIDC : révoquer le token auprès du fournisseur d'identité et en regénérer un.

### Scan de secrets

Un pre-commit hook `gitleaks` empêche de committer des secrets accidentellement :

```bash
uv run pre-commit install
```

### Signalement d'incident

En cas d'incident de sécurité (fuite de secret, accès non autorisé) :
- Révoquer immédiatement les accès compromis (étapes ci-dessus)
- Contacter le CERT ministériel (DINUM)
- Documenter l'incident (date, périmètre, actions prises)

---

## Développement

```bash
uv run pytest                # Lancer tous les tests
uv run pytest --cov          # Tests + rapport de couverture
uv run ruff check .          # Lint
uv run pyright               # Type check
uv run pre-commit run --all  # Hooks pre-commit (gitleaks, etc.)
```

Après modification du code, pour que Claude Desktop (ou une autre session Claude Code) prenne en compte les changements :

```bash
rm -rf .venv && uv venv && uv sync  # si besoin, recrée le venv
# Puis redémarrer le client MCP
```

---

## Architecture

```
mcp-docs/
├── src/mcp_docs/
│   ├── app.py              # FastMCP + lifespan
│   ├── client.py           # Client HTTP asynchrone (httpx)
│   ├── config.py           # Config Pydantic Settings
│   ├── exceptions.py       # Hiérarchie d'exceptions typées
│   ├── models.py           # Modèles Pydantic des réponses API
│   ├── resources.py        # MCP resources (docs://user, docs://documents)
│   ├── server.py           # Entry point + CLI --config-check
│   ├── tools.py            # Tools CRUD principaux
│   ├── tools_access.py     # Tools accès + invitations
│   ├── tools_ai.py         # Tools IA (transform + translate)
│   ├── tools_sharing.py    # Tools link config + favoris
│   └── tools_organize.py   # Tools move/duplicate/trashbin
└── tests/                  # 160+ tests (respx pour les mocks HTTP)
```

### Points clés

- **Client HTTP** : `httpx.AsyncClient` avec retry `tenacity` (exponential backoff sur 429/502/503/timeouts) et rate limiting par sémaphore
- **Auth duale** : mode `session` (cookie Django + CSRF token généré client-side) ou `oidc` (Bearer token)
- **Conversion markdown → Yjs** : pour mettre à jour le contenu, un document temporaire est créé et son Yjs pré-converti est transplanté sur le doc cible (contournement élégant pour supporter le markdown formaté sans client Yjs)
- **Erreurs typées** : `DocsAPIError` + sous-classes (`DocsAuthError`, `DocsNotFoundError`, …) avec mapping HTTP auto

---

## Ressources

- [Documentation Docs (La Suite numérique)](https://docs.numerique.gouv.fr/)
- [Repo upstream Docs](https://github.com/suitenumerique/docs)
- [Spec MCP (Model Context Protocol)](https://modelcontextprotocol.io/)
- [SDK Python MCP](https://github.com/modelcontextprotocol/python-sdk)

## Licence

MIT
