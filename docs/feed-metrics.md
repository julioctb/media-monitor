# Feed metrics follow the complete filtered result

The Feed's **Medios con noticias** and **Eventos** indicators now use
`GET /api/stats/feed`, not the global overview or the loaded page. This implements
T8.c / S13 without changing list results, grouping, classification or stored data.

## Query contract

The endpoint uses the same `ClientIdDep` and `_mention_filters` as `/api/mentions`.
It accepts `source`, `sentiment`, `keyword_id`, `since`, `until`, `q`, `classifier`,
`label` and `medium` with the list endpoint's types, defaults and validation.
Repeated `sources` selects a channel union; an explicit `source` intersects it.
Absent or empty source sequences are **unrestricted**, not match-none. Invalid
enums, datetimes, integers and overlong medium values return 422.

The Feed URL continues to accept only its existing filters. The loader expands
`political=1` to the political classifier/label probe. Source and medium override
channel pooling; medium still combines with an explicit source. Otherwise channel
members come from the global zero-filled source catalogue, including zero-count
members. A known empty resolved channel takes an explicit empty-list/zero-metric
path without issuing an unrestricted aggregate request.

Both requests receive the same normalized scalar values. `none` selects SQL NULL
only. Search retains title/content SQL wildcard semantics, not author/host/summary
search. Date-only bounds independently use the existing local-day helper, from
midnight through **23:59:59 inclusive**; no last-microsecond correction is included.
NULL publication dates fail bounded predicates. Reversed ranges remain 200 with
zero results, alongside the existing UI warning. Other invalid-input behavior is
unchanged. Limit, offset and ignored sort input cannot change the aggregate; the
wrapper never serializes pagination.

## Response and counted units

| Field | Meaning |
| --- | --- |
| `total` | Complete matching tenant-owned publications, once each. |
| `by_source` | Matching publication counts, zero-filled for the source enum. |
| `by_sentiment` | Matching publication counts with `positive`, `negative`, `neutral`, and explicit `none` for NULL. Tone is included, not self-excluded. |
| `news_medium_count` | Distinct legacy `_outlet_of` identities after excluding only the existing social-source set. |
| `result_group_count` | Distinct nonnull event IDs plus one group per eventless publication. Singleton events count. Event and mention identities are tagged to avoid numeric ID collisions. |

The reducer reads one filtered scalar projection, with classification `EXISTS`
rather than multiplying joins. It does not hydrate ORM relationships, query per
publication, fetch all frontend pages or sum per-source distinct counts.

**Legacy unit caveats are deliberate.** Outlet identity remains normalized host
(lowercase, stripped `www.`), author fallback, then `unknown`. Field hosts,
author/unknown and relay identities remain eligible under the old non-social
exclusion rule. This is not the S7 identified-newsroom diversity metric, independent
corroboration or a truth assessment. `Eventos` preserves the Feed's event-plus-loose
publication unit; it is not an Event-table count or a two-publication threshold.

## Empty, unavailable and navigation states

- A measured empty result displays zero indicators and the existing empty list.
- An aggregate-only error retains successful cards, results and controls. Metrics
  use a compact `—` marker with a “No disponible” title and an explicit status
  explanation, never zero, global totals or page groups.
- Publication text and pagination continue to use `mentions.total`.
- Sidebar medium/source figures remain global tenant navigation, labeled as not
  applying Feed filters. The global catalogue is not replaced by filtered counts.
- The list and aggregate are separate read requests. Concurrent ingestion can
  change data between them; this change does **not** promise an atomic snapshot.

## Verification boundary

Public request tests compare fixture-derived counts and complete matching mention
IDs, including filter combinations, tenant isolation, source unions, null/date
boundaries, strict errors and pagination invariance. Wrapper, real loader and
mounted Feed tests cover encoding, precedence, zero versus unavailable, retained
cards and unchanged controls. Built HTTP/CSS and native browser verification are
separate parent-owned gates; unit tests do not establish browser layout or real
model quality. No summary/history, taxonomy, versioning, authentication, approval,
provider or V3 redesign work is included.
