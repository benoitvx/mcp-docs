# Todo — Prochaines étapes

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
- [x] 161 tests (lint + pyright + pytest + pip-audit + gitleaks en CI)
- [x] Fix CVE-2026-40347 (python-multipart bumped à 0.0.26)
- [x] README complet avec les 25 tools, 4 workflows, architecture, sécurité ANSSI
- [x] Évaluations MCP — `evaluation.xml` avec 10 Q&A pairs (placeholders à remplir)

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
- **Tools non-idempotents marqués destructive=True** : delete, revoke_access, update_access, remove_favorite, move, update_link_configuration.
