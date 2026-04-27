# Todo — Prochaines étapes

## 🎯 Tâche en cours — Restreindre `docs_delete_document` au créateur

- [x] Étendre `DocumentSummary` avec un champ `creator: str | dict | None`
- [x] Ajouter `DocsClient.get_document(document_id)` (GET `/documents/{id}/`)
- [x] Modifier `docs_delete_document` : 2 GET (document + me) puis comparer `creator`/`me.id` avant DELETE
- [x] Fixtures de test (`SAMPLE_DOCUMENT_DETAIL`, `SAMPLE_DOCUMENT_DETAIL_OTHER_CREATOR`)
- [x] Tests tools (succès créateur, succès dict, refus non-créateur, refus creator manquant, 404)
- [x] Tests client pour `get_document`
- [x] Mise à jour CLAUDE.md (table tools + endpoint)
- [x] `uv run ruff check . && uv run pyright && uv run pytest` (180 tests OK, lint/pyright clean)

### Résultat

`docs_delete_document` refuse désormais toute suppression d'un document dont l'utilisateur authentifié n'est pas le créateur. Mécanique : avant le `DELETE`, le tool fait `GET /documents/{id}/` puis `GET /users/me/`, extrait `creator` (str ou `{"id": ...}`) et compare avec `me.id`. Si pas de match (ou `creator` absent), retour `"Error: you can only delete documents you created."` sans appel `DELETE`. La couche transport (session/CSRF aujourd'hui, OIDC plus tard) n'est pas affectée.

Fichiers modifiés : `src/mcp_docs/models.py`, `src/mcp_docs/client.py`, `src/mcp_docs/tools.py`, `tests/conftest.py`, `tests/test_tools.py`, `tests/test_client.py`, `CLAUDE.md`.

Test E2E (Claude Desktop, 2026-04-27) ✅ :
- Création + suppression d'un doc créé par soi → corbeille OK.
- Suppression d'un doc partagé ("tonton du bled", non-créateur) → refus client-side, pas de DELETE.
- UUID `00000000-…` (placeholder renvoyé par le backend Docs au lieu d'un 404) → également refusé. Défense en profondeur confirmée.

---

## ✅ Fait

### Fondations
- [x] Config Pydantic Settings (`DocsConfig`) — remplace `os.environ.get()` éparpillés, validation `env_prefix=DOCS_`, contraintes sur retries/concurrent
- [x] Modèles Pydantic typés (`DocumentSummary`, `DocumentContent`, `PaginatedResponse[T]`, `UserInfo`, `DocumentAccess`, `Invitation`) — fini les `dict` bruts
- [x] Hiérarchie d'exceptions (`DocsAPIError` + `DocsAuthError` / `DocsPermissionError` / `DocsNotFoundError` / `DocsValidationError` / `DocsRateLimitError`) avec mapping HTTP auto
- [x] Retry logic — tenacity, retry sur 429/502/503/timeout, exponential backoff
- [x] Rate limiting — `asyncio.Semaphore`, max 5 requêtes concurrentes
- [x] CLI `--config-check` pour valider config + auth sans lancer le serveur MCP
- [x] MCP Resources (`docs://user`, `docs://documents`)

### Tools CRUD & recherche
- [x] `docs_list_documents` — liste paginée
- [x] `docs_get_document_content` — markdown / html / json
- [x] `docs_create_document` — depuis markdown (multipart, conversion backend)
- [x] `docs_search_documents` — par titre ou contenu
- [x] `docs_get_me` — infos user authentifié
- [x] `docs_list_children` — sous-documents

### Tools édition
- [x] `docs_update_document_title` — renommer (PATCH JSON)
- [x] `docs_update_document_content` — **avec markdown formaté** via trick temp-doc + transplant Yjs (pas besoin de pycrdt côté client)
- [x] `docs_delete_document` — soft delete (corbeille)

### Tools accès/permissions
- [x] `docs_list_accesses`, `docs_grant_access`, `docs_update_access`, `docs_revoke_access`
- [x] `docs_list_invitations`, `docs_create_invitation`

### Tools IA (natifs Docs)
- [x] `docs_ai_transform` — correct, rephrase, summarize, beautify, emojify, prompt
- [x] `docs_ai_translate` — ISO language code

### Tools partage par lien
- [x] `docs_update_link_configuration` — restricted / authenticated / public + rôle

### Tools favoris & organisation
- [x] `docs_list_favorites`, `docs_add_favorite`, `docs_remove_favorite`
- [x] `docs_move_document` — positions first-child/last-child/left/right/siblings
- [x] `docs_duplicate_document` — avec/sans descendants + accesses
- [x] `docs_list_trashbin`, `docs_restore_document`

### Qualité & CI
- [x] 175 tests (lint + pyright + pytest + pip-audit + gitleaks en CI)
- [x] Fix CVE-2026-40347 (python-multipart bumped à 0.0.26)
- [x] README complet avec les 25 tools, 4 workflows, architecture, sécurité ANSSI
- [x] Évaluations MCP — `evaluation.xml` avec 10 Q&A pairs (placeholders à remplir)

### Cookie session — rotation automatisée (avril 2026)
- [x] Module `paths.py` — résolution XDG (`~/.local/state/mcp-docs/session.json`, profil Chromium sous `~/.local/share/mcp-docs/browser-profile/`)
- [x] `load_config()` + `read_session_file()` dans `config.py` — précédence `DOCS_SESSION_COOKIE` > `DOCS_SESSION_FILE` > défaut XDG, `model_validator` reste pur
- [x] CLI `mcp-docs-refresh-session` — fast-path HTTP (probe `/users/me/`) + fallback Playwright avec profil persistant, écriture atomique `0600`
- [x] Flag `--headless` + notification macOS `osascript` sur échec (runs planifiés)
- [x] Extra optionnel `[browser]` pour Playwright (pas imposé aux autres users)
- [x] 14 nouveaux tests (`tests/test_session_file.py`) — parsing + précédence
- [x] Plist launchd horaire documenté dans README, activable en 3 commandes `launchctl`
- [x] README « Rotation des secrets » mis à jour, bloc Claude Desktop nettoyé (plus de cookie en dur)

---

## 🚧 À faire

### P0 — Migration auth OIDC
- [ ] Migrer le client vers `/external_api/v1.0/` avec auth OIDC Bearer token
- [ ] Intégrer ProConnect (authorization_code flow) pour obtenir le token
- [ ] Supprimer le hack CSRF (plus nécessaire avec Bearer token)
- [ ] Mettre à jour les tests et la doc

Ref : issue [suitenumerique/docs#1703](https://github.com/suitenumerique/docs/issues/1703), PR [#1923](https://github.com/suitenumerique/docs/pull/1923)

Bloqué : attendre le token exchange côté La Suite (@jmaupetit).

### P1 — Distribution
- [ ] Publier sur PyPI (`pip install mcp-docs` ou `uvx mcp-docs`)
- [ ] Workflow GitHub Actions pour release auto (tag → build → publish)
- [ ] Documentation installation via PyPI dans le README

### P2 — Robustesse & gouvernance
- [ ] Remplir les placeholders dans `evaluation.xml` avec un compte de test stable
- [ ] Ajouter le pre-commit hook gitleaks (`uv run pre-commit install` documenté mais à vérifier sur CI)
- [ ] Configurer le repo GitHub (branch protection) — nécessite GitHub Pro ou repo public
- [ ] Ajouter des évals pour les nouveaux tools (IA, partage, organisation)

### P3 — Fonctionnalités additionnelles
- [ ] `docs_upload_attachment` — upload de fichiers/images (endpoint `/attachment-upload/`)
- [ ] `docs_list_versions` + `docs_get_version` — historique du document
- [ ] `docs_comment` / `docs_list_threads` — collaboration asynchrone
- [ ] `docs_ask_for_access` — demander l'accès à un doc (workflow utilisateur)

---

## Notes

- **Markdown update sans pycrdt** : on exploite le convertisseur backend en créant un doc temporaire, en récupérant son Yjs pré-converti, et en le transplantant sur le doc cible. Pas de parser markdown → BlockNote côté client nécessaire. Coût : 4 appels API par update au lieu d'1.
- **Auth session + CSRF** : hack temporaire. Le CSRF token est généré côté client (64 chars hex via `secrets.token_hex(32)`), injecté en cookie + header `X-CSRFToken` + `Referer`. Partira avec la migration OIDC.
- **Rotation cookie via Playwright** : palier intermédiaire en attendant l'OIDC. Évite le DataPass ProConnect (4 rôles + 5j ouvrés) trop lourd pour un outil mono-utilisateur. Profil Chromium persistant → la session ProConnect IdP est réutilisée → refresh silencieux dans 99% des cas. Notifications macOS quand la re-MFA est requise.
- **Tools non-idempotents marqués destructive=True** : delete, revoke_access, update_access, remove_favorite, move, update_link_configuration.
