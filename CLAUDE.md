# CLAUDE.md — engineering guidelines

This file is read by Claude Code at the start of every session. It records the
non-negotiable working rules for this repository.

## Branch & PR hygiene

- **One PR per logical change.** Do not stack unrelated work on the same branch.
  If a task naturally splits (e.g. backend + frontend), open separate PRs on
  separate branches.
- **Each PR gets its own branch.** Branch names follow the pattern
  `claude/<short-description>` (matches the harness convention) or
  `<author>/<short-description>` for human authors.
- **Open PRs as drafts** until the work is complete and locally verified. Mark
  ready for review only after CI is green and the test plan in the PR body is
  walked through.
- **No force-push to shared branches.** If history reconciliation is needed
  (e.g. unrelated histories, accidental commit), prefer a merge commit or a
  fresh branch over rewriting history that someone else might already have
  fetched.

## GitHub API budget

The GitHub MCP connection runs on Stefan's personal account quota
(5,000 requests/hour, shared with everything else on his account) until a
bot account exists. Be frugal — hitting the limit blocks all merges for
up to an hour:

- **No polling.** CI failures arrive as webhook events; success is the
  absence of one. At most ONE `get_check_runs` after a fixed wait
  (~80 s), then act.
- **Undraft + merge back-to-back**, no status reads in between.
- **No redundant reads** (`get`, `list`, `search`) when the answer is
  already known from a webhook, a prior call, or local git.
- On a rate-limit error: bounded waits (~10 min), don't hammer. Batch
  any queued merges into the window when it reopens.

## Commits

- **Conventional, why-focused messages.** First line ≤72 chars, imperative
  mood. Body explains *why* the change is needed, not *what* the diff shows —
  the diff already shows the what.
- **Atomic commits.** Each commit should leave the repo in a working state.
  Don't mix refactors with feature work in a single commit.
- **No `--no-verify` and no signing bypass** unless the user explicitly asks
  for it. If a hook fails, fix the underlying problem.

## Code

- **Edit existing files in preference to creating new ones.** Don't add a new
  module when an existing one fits.
- **Don't write speculative abstractions.** Wait for the third repetition
  before extracting a helper. Three concrete sites are clearer than one
  premature interface.
- **Validate at boundaries only.** Trust internal code; don't pepper the
  codebase with defensive checks for impossible states.
- **Comments explain *why*, not *what*.** Skip comments where the code is
  self-evident. Don't reference task IDs, PR numbers, or "added for X" — that
  belongs in commit messages and rots in code.
- **Match the surrounding style.** Read neighbouring files before introducing
  a new pattern.

## Testing

- **New behaviour ships with a test.** If it can't be tested, say so in the PR
  rather than skipping the test.
- **Don't claim a UI feature works without exercising it in a browser.**
  Type-checking and unit tests verify code correctness, not feature behaviour.
- **Tests are not optional infrastructure.** Treat the test suite as
  production code: clear names, no flakiness, no commented-out tests.

## Reviewing your own work

Before marking a PR ready or claiming a task complete:

1. Read the diff end-to-end. Look for debug prints, dead code, half-finished
   changes, accidental file deletions.
2. Run the tests locally if practical. State explicitly in the PR body if you
   couldn't.
3. Check for security regressions (input validation, secret leakage, SQL
   injection). Defaults: parameterised queries, no string concatenation into
   SQL or shell, no logging of credentials.
4. Verify the PR's stated test plan is achievable with what's checked in.

## Domain rules (brewery-specific)

- **All beer volumes are in hectoliters (hl).** 1 hl = 100 l. Never mix units
  silently. If a number could be ambiguous, label it.
- **Terminology: the plural of Sud is "Sude"** (not "Süde") — in docs, UI
  strings, and comments alike. The DB table is already named `sude`.
- **Recipes are versioned and immutable.** Edits create a new row with
  `version + 1`; existing Sude keep their original recipe link. Confirmed
  2026-08: already-scheduled Sude never re-link to newer versions.
- **Tank double-booking is prevented at the database level** via the GiST
  `EXCLUDE` constraint on `tank_occupancy` — scoped to fermentation and
  storage. Ausschank tanks legally blend several batches (confirmed
  2026-08, issue #13: 6×30 hl → 100+80 hl); there the rule is
  sum-of-allocations ≤ capacity, enforced in the application at every
  mutating endpoint. Phase-2 validation blocks hard — no override
  mechanism.
- **Blending is sortenrein** (confirmed 2026-08-05): only batches of the
  SAME `beer_style` ever share an Ausschank tank — mixing styles is a
  hard 409 in transfer and schedule, never a warning.
- **30-hl merged batches are real** (confirmed 2026-08, issue #3): the same
  recipe is brewed twice within 48 h and merged into one 30-hl tank. Until
  Phase 2 models this explicitly, the `EXCLUDE` constraint blocks the second
  occupancy — do not "fix" that by relaxing the constraint.
- **Two Sud numbers, both load-bearing.** `global_number` is Vincenz'
  jahresübergreifende Zählung (2026 = 210…300; new Sude continue at 301)
  and is shown as "Sud 285". `style_year_number` is the per-style count
  shown as "Kellerbier Hell 28/2026". Never conflate them.
- **The complete Sud history (Nr. 1–300, 2021–2026) is seed data**:
  `backend/scripts/extract_sudplan.py` → `data/sudplan_*.json` →
  `sudplan_import.py` at seed time. Mapping decisions live in that
  module's docstring — notably "Striezitank" IS the Bergtank 120 hl,
  "Entlas" IS the Bergtank 100 hl (same physical tank), "Bock" (Sud 1)
  IS the Weizenbock, and "Bergbier (Gisela)" IS the Festbier. Sude 1–138
  are short-form history (date, Sorte, Gärtank only). Tests
  run on the small demo world (`seed(demo_sude=True, sudplan=False)`);
  only `test_sudplan_import.py` loads the real history, pinned to
  Stichtag 2026-08-05.
- **Primary usage is mobile, in the cellar, with spotty connectivity**
  (confirmed 2026-08, ROADMAP §2.8). Every user-facing feature ships
  mobile-first; the app is a PWA with offline read cache and a queued-
  mutation strategy. Desktop is the derivative view.

## Out of scope (do not build without explicit ask)

These are recorded in `ROADMAP.md` §6.5 and repeated here so they don't drift
back in:

- Native mobile app, multi-brewery, ingredient inventory, POS-as-a-service,
  microservices, IoT tank sensors. The mobile-first PWA is the delivery
  model (no App-Store app); single tenant; Excel import suffices.

## When in doubt

Ask. A 30-second clarifying question is cheaper than a 30-minute wrong turn.
