# Preserve substantive event titles

A pipe alone is not evidence that the following text is a publisher name.
`Institution | Opens library` and `Institution | Closes hospital` describe
different occurrences and must not collapse to `Institution` during event
matching or presentation.

## Normalization boundary

- Preserve pipe-separated headline content, without institution-specific rules.
- Continue removing dash-introduced publisher signatures. A following pipe may
  belong to that signature: `Headline - Publisher | Local section` becomes
  `Headline`.
- An ambiguous pipe-only publisher suffix may remain visible. Retaining extra
  metadata is safer than deleting the substantive description of an occurrence.
- Keep original publication titles unchanged. The helper supplies comparison
  variants and display titles; it does not rewrite stored source text.
- Preserve existing similarity thresholds, client isolation, time windows,
  canonical/media preference and title-pool matching.

## Verification

`backend/tests/test_events.py` exercises public assignment of library-opening
and hospital-closing publications with different institutional prefixes, with
and without dash-introduced publisher chains. The same tests check original
title retention, separate event counts and prompt/display title preservation.
Existing same-story publisher-suffix and window/client controls remain in force.

The scorer remains heuristic and still takes the maximum of plain-title and
normalized-title similarity. Shared publisher wording can independently raise
the plain score above the existing threshold. This fix does not guarantee
semantic event identity or change that separate behavior; historical repair
must therefore use reviewed source evidence, not automatic score-based moves.

This is a local source correction, not a historical repair or deployment.
Existing wrong links require a separately reviewed, backed-up repair manifest.
In the political-analysis work, S14 authorizes only confirmed incorrect links
for publications included in client1's 18 preserved report windows from
October 9 through October 26, 2026; original titles, texts and dates must remain
unchanged. No blanket event rebuild is authorized.
