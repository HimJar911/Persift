# Ontology debt

Tracked list of genuine ambiguities from the corpus-extension pass
(full-Greenhouse-volume re-run, Jul 2026) that should NOT be force-fit into
a category or a real/junk bucket. Per `FORM_ENGINE_DESIGN.md`'s standing
rule against force-fitting ambiguous cases — abstaining/flagging is correct
when confidence is genuinely low. Add to this file rather than inventing a
bad-fit category or bucket assignment just to close something out.

## 1. `reflexivity.firststage.co` — single unlabeled file-input extraction gap

**6 job_ids** (Toggleai company postings: `5018731007`, `5018743007`,
`5021397007`, `5033842007`, `5147331007`, `5147333007`), all on
`https://reflexivity.firststage.co/jobs?gh_jid=...` — a non-standard
Greenhouse embed domain (not `job-boards.greenhouse.io` /
`boards.greenhouse.io`).

Every one of these extracted to exactly ONE field: a bare
`<input type="file">` with no discoverable label via any of the 5 label
strategies, no other fields captured at all.

**Not resolved as either `likely_real` or `likely_junk`** during the
real-vs-junk triage (`corpus_analysis/triage_real_vs_junk_resolved.json`,
bucket `extraction_gap`) — it's clearly not job-board chrome (no filter
widgets, no department checkboxes, no search/language-switcher pattern seen
elsewhere in confirmed-junk records), but a single unlabeled field isn't
enough to confirm it's a real, well-formed application form either.

**Open question for whoever picks up P1.3/P1.4 or re-crawls this domain:**
is `firststage.co` a legitimately different rendering path that the
harvester's extraction JS doesn't handle correctly (e.g. the real form
loads behind additional JS/a different DOM structure this embed variant
uses), or is the file input itself the ONLY real field on an otherwise
sparse form? Needs a live look at the rendered page (not just the saved
manifest data) to resolve — flagging rather than guessing.

## 2. `hidden_tracking_field` — provisional structural pattern, not fully enumerated

Added to `taxonomy_v1.py`'s `STRUCTURAL_PATTERNS` during Step 3/4 of the
full-volume corpus extension. Full-volume clustering surfaced large
(~3,700-4,700 field), consistently `itype=hidden` clusters per distinct
marketing/analytics parameter name: `gclid`, `ft_source`, `ft_campaign`,
`ft_content`, `ft_medium`, `ft_term`, `lt_source`, `lt_campaign`,
`lt_content`, `lt_medium`, `lt_term`, `lead_source`, `lead_source_details`,
`gaclientid`, `gauserid`, `gatrackid` (all Monks-company postings in the
sample checked). Not present as a class in the original 767-job seed
sample at meaningful volume — a real category the larger harvest actually
found, exactly what Step 4's "provisional enum, expect additions" framing
anticipated.

**Not yet resolved to a final list of specific field names** — currently
handled as one blanket structural pattern (skip, don't classify as an
askable question) rather than individually enumerating each tracking
parameter. Fine for now since none of these are ever real user-facing
questions regardless of the exact parameter name, but if a future session
wants per-field-name granularity (e.g. for telemetry/debugging which
specific hidden fields appear on which ATS pages), this needs its own pass.

## 3. Two clustering false-merge bugs found and fixed at full volume (for context, not open)

Not open questions — documented here only so a future re-run of
`auto_cluster_v2.py` from scratch doesn't reintroduce them. See
`auto_cluster_v2.py`'s inline comments (`_GENERIC_LABEL_TEXT`, the
`form-` prefix handling in `normalize_id`) for the fixes:

1. A react-select required-shim's "Select..." placeholder text, captured
   via the `preceding-text` label strategy, false-merged 106,946 fields
   across hundreds of companies into a fake "select" topic cluster before
   the fix.
2. Greenhouse's generic `form-question_<jobid>` id wrapper false-merged
   709 distinct real questions into one fake 5,516-field cluster before
   the fix (id-normalization didn't strip the `form-` prefix before
   checking the generic-stem denylist).

Both are the same underlying failure shape as the original
department_interest/location_preference correction documented in
`corpus_analysis/README.md` — a reminder that this class of bug (generic
chrome text/id false-merging across companies) should be actively
hunted for, not just fixed reactively, whenever clustering re-runs at a
new volume.

## 4. Non-English residue explicitly excluded from Step 5 (scope decision, not a gap)

10,167 fields remained in residue after Step 3's fixes; two exclusions were
applied before Step 5's LLM classification pass, both founder-confirmed:

- **1,863 fields**: the known malformed empty-record harvester artifact
  (`field_id_hash == "709446a2"`, `tag: null`, every attribute null —
  already documented in `corpus_analysis/README.md` from the original
  767-job pass, where it appeared 12x; confirmed identical shape at full
  volume). Not real content, excluded outright.
- **2,712 fields**: labels containing Korean/Japanese/Chinese script,
  concentrated in 368 job_ids across 8 companies (Coupang, Riot Games,
  Krafton, Moloco, OKX, Adyen, SIEI, and one unlabeled company). Greenhouse
  has no structured country field at all (confirmed dead end,
  `corpus/README.md`), so label language is effectively the only available
  signal. **Deliberately excluded, not deferred as a gap** — Persift's
  product scope is US-focused early-career hiring, and these are plausibly
  non-US-targeted postings/application variants from companies with real
  Asia-market operations. `taxonomy_v1` and the original 767-job pass were
  both built entirely from English-language forms; extending either to
  non-English content was judged out of current scope rather than
  something to solve incidentally inside this corpus-extension pass.

Remaining in scope for Step 5: **5,378 fields** (`residue_for_llm_pass.json`'s
`kept` list, after a follow-up fix — see entry 5 below) — genuine
English-language residue that didn't cluster deterministically, the actual
target for LLM-assisted classification.

## 5. `file-attachment` hidden field (Monks, 546 instances) — genuinely ambiguous, not classified

`field_id_hash == "a1b0357"`: `tag: input`, `itype: file`,
`name: "file-attachment"`, `vis: false`, `section: "Uploads"`,
`nearby: "Attach undefined"`. Appears 546 times, but on exactly **1
company** (Monks) across 546 of its job postings — a per-company template
artifact, not a cross-company pattern.

Checked whether these pages ALSO have a separate, real, visible resume
field: **no** — none of the 312 distinct Monks postings carrying this field
have any other file-upload field. So this hidden input is either (a) the
company's actual (mis-rendered) resume-upload mechanism, real but broken —
"Attach undefined" reads like an un-interpolated template variable, a bug
on Monks's own career-site template, not a harvester bug — or (b) genuinely
dead/inert markup that never becomes interactive.

**Not classified as `resume_upload` or any other category** — `vis: false`
means it wasn't confirmed fillable in a live browser session at crawl time,
and forcing a category here would be exactly the kind of guess
`FORM_ENGINE_DESIGN.md`'s standing rules warn against. Flagged for whoever
next investigates Monks-specific rendering (or re-crawls with a step that
tries triggering whatever reveals this field, if anything does).

## 6. Field-level junk chrome found during residue review (excluded, not classified)

Two more confirmed-junk patterns found while working through Step 5's
residue, both field-level (a junk widget embedded on an otherwise-real
application page — Step 2's page-level triage can't catch these):

- **`field_id_hash == "b00f6f0d"`, 246 instances, 100% `andurilindustries`**
  — a department/location/employment-type filter combobox (`nearby` text
  literally concatenates "DEPARTMENT" + a list of department names, or
  "LOCATION" + city names, or "EMPLOYMENT TYPE" + Contract/Full-time/
  Intern/Temporary). Same job-board filter widget already documented in
  `corpus_analysis/README.md`'s original open-coding pass for this exact
  company (`andurilindustries`, "open-roles-list" widget) — these are just
  the same widget appearing on Anduril's newly-harvested second-run
  postings. Excluded from residue, not classified as a topic category.
- **A malformed-extraction shape** (`tag`, `id`, `name`, `role` all
  literally `null`) that isn't limited to the single `709446a2` hash
  already documented — 36 distinct hashes share the identical all-null
  structural signature, 34 of them singleton occurrences (count=1) plus
  the 2 recurring ones (`709446a2`: 1,862x; `87775d4e`: 393x, itself a
  mix of Monks cookie-consent-banner chrome and one Anduril Gem-platform
  terms-notice, both non-interactive). Since `field_id_hash` is defined
  purely from structural DOM attributes and all of these are null on every
  attribute, the hash can't discriminate between genuinely different pages'
  malformed-extraction artifacts — but the shared "everything is null"
  shape itself is a reliable enough signal that none of these are real
  content. All 1,883 total instances excluded from residue as harvester/
  extraction artifacts, not fed to Step 5's classification pass.
- **A genuine `field_id_hash` collision between two different widgets**:
  164 instances of hash `8e474141` (otherwise the confirmed
  react-select-required-shim, 132,391 real instances) turned out to be
  Anduril's site-wide search box instead — same
  `tag=input, htmlType="", name="", id="", autocomplete="", role=""`
  structural signature (which is all `field_id_hash` is computed from,
  per `FORM_ENGINE_DESIGN.md` §3.6a), but `required=False` and
  `placeholder="SEARCH ANDURIL"` where the real shim always has
  `required=True` and an empty placeholder. Caught because the shim
  clustering rule's `req is True` guard correctly excluded them, and a
  by-hand check of the excluded remainder surfaced the collision rather
  than assuming they were just more shim instances. **Real finding worth
  keeping in mind for P1.3/P1.4**: `field_id_hash` alone is not always
  sufficient identity — it can collide between semantically unrelated
  widgets when their coarse structural attributes happen to match.
  Excluded from residue as confirmed junk widget chrome (Anduril's own
  in-page search box), not classified as a topic category.
