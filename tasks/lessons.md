# Lessons Learned

## Django CSRF avec session auth

**Erreur** : POST sur l'API Docs retourne 403 "CSRF cookie not set".
**Cause** : Django exige un cookie `csrftoken` + header `X-CSRFToken` + header `Referer` pour les POST avec auth par cookie de session. L'API ne renvoie jamais le cookie CSRF.
**Solution** : Générer un token de 64 chars côté client (`secrets.token_hex(32)`), l'injecter comme cookie et header.

## Cookie de session Docs

**Erreur** : Auth échoue avec le cookie `sessionid`.
**Cause** : Le cookie s'appelle `docs_sessionid`, pas `sessionid`.
**Règle** : Toujours vérifier le nom exact du cookie dans le navigateur (DevTools > Application > Cookies).

## uv sync casse le .venv sur iCloud

**Erreur** : `ModuleNotFoundError: No module named 'mcp_docs'` après `uv sync`.
**Cause** : `~/Dev` est un symlink vers iCloud. `uv` mélange les chemins réels et symlinks.
**Solution** : `rm -rf .venv && uv venv && uv sync` puis relancer Claude Code.

## pip audit vs pip-audit

**Erreur** : CI échoue avec `unknown command "audit"`.
**Cause** : `pip audit` n'existe pas — la commande est `pip-audit` (package séparé).
**Règle** : `pip-audit` est un outil standalone, pas une sous-commande pip.
