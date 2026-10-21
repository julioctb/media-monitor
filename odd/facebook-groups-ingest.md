# facebook-groups-ingest

**Objective:** ingest Facebook GROUP content (and keep pages working) via Graph API, so `https://facebook.com/groups/1090003732034388` becomes a monitorable source. Page flow unchanged.

**Problem:** `FacebookPageAdapter` only calls `GET /{page-id}/posts` (page token). The second requested source is a group → needs `/groups/{id}/feed` + user token with group perms. A `kind` discriminator on the existing credential is the minimal surface: same list, same adapter, same UI row.

**Constraints:**
- `MentionSource.facebook_page` reused for groups — NO enum/DB migration.
- `POST /settings/test-facebook` probe unchanged (`GET /{id}?fields=name,link` resolves pages AND groups).
- `worker.py` untouched (adapter branches internally).
- Backward compat: rows without `kind` behave as `page` (Pydantic default).

**Tasks:**
- [x] T1 (tests, RED): group cases in `backend/tests/test_facebook_page.py` mirroring page cases — kind group hits `/groups/{id}/feed`; parse group payload (message→content, first line→title, label wins over from); fallback URL `https://www.facebook.com/groups/{gid}/posts/{suffix}` (suffix = part after first `_` when id contains `_`, else full id; best-effort, verify with live token); default kind absent → page path (existing tests untouched stay green = compat proof).
- [x] T2 (GREEN): `FacebookPageCredentials.kind: Literal["page","group"] = "page"`; `posts_url` + fallback-url branch by kind; parse shared.
- [x] T3 UI: `frontend/src/lib/api.ts` FacebookPage +`kind?: 'page'|'group'`; `routes/settings/+page.svelte` fb row gains Página/Grupo select (default Página), persisted through save path (form ids `fb-page-${i}` pattern — reconstruct incl. kind), section copy mentions grupos.
- [x] T4 verify: `../.venv/bin/python -m pytest backend/tests -q` all green; `cd frontend && npm run check`.

**Pending (blocked on Julio's token — NOT part of this diff):**
- Classify `61593006365773` (page vs personal profile) via `GET /{id}?fields=type,metadata` once any token exists. If personal profile → follow-up kind `user` (`/{id}/feed`), one branch.
- Live verify both sources: probe + one ingest cycle (`docker logs … facebook_page`), real inserted counts.
- Token lifetime: if short-lived, extend via `fb_exchange` (needs app id+secret in env — ask Julio).

**Route:** delegated writer (4 files, 2+ non-trivial). Risk: medium (ingest path, live data) → writer self-verifies with full backend suite + svelte check; parent spot-checks one command.

**Progress:** T1-T4 landed on `feat/facebook-groups`, commit `5cdbad123e867bfb06b00d64ac77d7ed7cdfbf30`; pending items stay blocked on the token.
