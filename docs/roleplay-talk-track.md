# Role-play talk track — ICU Step-Down Readiness

For the **Submission → AI role-play** (Customer Skills domain). One session, two
AI personas in the room, 20–30 minutes. You walk through the solution once,
make the value case, and handle questions from both.

| Persona | Likely title | What they fund / live with | Their KPIs |
|---|---|---|---|
| **Business stakeholder** | CMO / VP Clinical Operations | Funds the pilot | ICU LOS, bed occupancy, emergent-admission wait / diversions, safe-transfer rate, cost per case |
| **Technical stakeholder** | VP Data & Analytics / Enterprise Architect / CMIO | Has to run it | Time to value, governed reuse, security & PHI, integration with the EHR, model risk & monitoring |

Scoring reminders (from the brief): **demo setup**, **tell-show-tell**, **value at
executive altitude**, **reading the room** (right altitude per asker, switch
mid-answer), **professional handling of objections**.

---

## 0. Pre-flight (15 min before)

The serving endpoint is **scale-to-zero** — a cold start mid-demo is the single
biggest live risk.

- [ ] **SQL warehouse is running** (Genie needs it; it once failed to start for ~10 min with `ALLOCATION_TIMEOUT_NO_UNALLOCATED_CLUSTERS`). Start it from the SQL Warehouses page and confirm it reaches *Running*.
- [ ] **Pipeline is running** (continuous): `databricks pipelines get 9d6181f7-d1bb-48ba-8501-3126ff309c70 --profile icu-sandbox` → `RUNNING`. Start it if you stopped it to save cost; give it ~5 min.
- [ ] Open the app and load the census once (warms `icu-readiness` + the app): https://icu-step-down-7474645901826067.aws.databricksapps.com
- [ ] Pick the patient for Segment B **on the day** (rule in §3) — rankings move as the live replay advances.
- [ ] Open **Analytics**; check what the drift tile shows (see §3, Segment C note).
- [ ] Open the Genie space in a tab and run the first question once: `/genie/rooms/01f1c3c57e2d129db3d00e5882886406`
- [ ] **Live-stream moment (Segment D2):** know where the replay is (`SELECT MAX(hours_released) FROM icu_step_down.landing.replay_clock`). If it's at 24h, the window is fully replayed — reset (truncate the three `landing` tables, then full-refresh `bronze.chart_events`) the day before.
- [ ] Deck open on slide 1 (`deck/icu-step-down-readiness.pdf`).
- [ ] Keep `evidence/` / `VALIDATION.md` one tab away for "prove it" questions.

## 1. Timing plan (≈25 min)

| Block | Time | Altitude |
|---|---|---|
| Open + agenda + confirm priorities | 2 min | Exec |
| Demo setup (customer, problem, what you'll show) | 2 min | Exec |
| Demo: A census → B patient → C analytics → D Genie → D2 live stream → E platform | 11–13 min | Tell (exec) · Show · Tell (exec), with 1–2 technical asides |
| Land the value + the ask | 3 min | Exec |
| Q&A / objections | 6–10 min | Switch per asker |

If time is squeezed: drop Segment E (platform) to a 30-second verbal and let
the technical stakeholder pull it out in Q&A. Keep D2 (live stream) if the
technical stakeholder said "running in production" was their concern.

---

## 2. Open and demo setup (≈4 min) — *deck slides 1–4*

**Open (to both, ~45 s).**
> "Thanks for the time. I've got about twenty minutes of content and I want to
> leave real time for your questions. The goal today: show you a working way to
> free ICU capacity without compromising safety, and agree whether it's worth a
> 60–90 day pilot in one of your units."

**Confirm priorities — one question each (this is "reading the room" early).**
> To the business stakeholder: "Before I start — is the pressure today mostly
> capacity (diversions, boarding in the ED, postponed electives) or cost per case?"
>
> To the technical stakeholder: "And on your side — is the bigger concern getting
> data out of the EHR, or governing and running a model once it's in production?"

Use their answers to choose which segment to linger on. Repeat their words back
later ("you mentioned diversions…").

**Frame the problem (slide 2–3, ~1 min).**
> "Your ICUs run at 70 to 90 percent occupancy. At that level, one bed held a day
> longer than needed is the bed you don't have for the next emergent admission.
> Today the step-down call is made on rounds, by memory and judgment, and it
> varies by provider and by shift — so the system defaults to 'keep them to be
> safe.' Each extra day is unreimbursed cost under DRG contracts, and it shows up
> on your LOS benchmarks against peers."

**Name the outcome (slide 4, ~30 s).**
> "What we're aiming for is a 10 to 15 percent reduction in ICU length of stay,
> with the safe-transfer rate held or improved. Not by automating discharge —
> by giving the team a consistent, explainable shortlist every shift."

**Tell — what you're about to show (~30 s).**
> "I'm going to show you four things in this order: the ranked census a charge
> nurse or intensivist would open on rounds; one patient's detail, so you can see
> *why* the tool says what it says; the analytics view leadership would watch;
> and how an operations manager asks questions in plain English. Then I'll take
> ninety seconds on the platform underneath, because that's what makes it
> trustworthy and repeatable."

**Data honesty line — say it up front, it pre-empts the hardest objection.**
> "One thing to be clear on: this runs on MIMIC-III — real, de-identified ICU data
> from a US academic medical centre, about 61,000 ICU stays. The 'current census'
> is 40 recent stays standing in for a live unit — and to make it behave like one,
> their last day of vitals is replayed into the pipeline in real time. Dates of
> birth are removed and patient IDs are masked before anything reaches this screen.
> Nothing here is your data yet; the pilot is where it becomes your data."

---

## 3. The demo — tell · show · tell

### Segment A — Ranked census (≈3 min) — *app home*

**Tell.** "First: who could move today?"

**Show.**
- Point at the bands: 40 patients, **Ready / Borderline / Not ready** (today: 13 / 13 / 14).
- Explain the number on each row: "This is a **relative readiness index, 0 to
  100 — a rank within the current census**, not a probability. 90 means 'more
  ready than 90 percent of the unit right now.'"
- Point at the vent / pressor indicators on the row.
- Patients show as **#P-…** — "that's a pseudonym, not the MRN; the app never
  receives a raw identifier." (Hold the detail for the architect.)

**Tell (business landing).**
> "On rounds, this turns 'who should we think about stepping down' from a
> forty-bed memory exercise into a ten-second scan. The value isn't that the
> tool decides — it's that every shift starts from the same evidence, so the
> decision stops varying with who's on."

### Segment B — Patient detail (≈3 min) — *click a patient*

> **Pick the patients on the day, by rule:** (1) a **Ready** row whose top factor
> is clinical (GCS, urine output, a lab) rather than age; then (2) a **capped**
> row — high index but *Borderline*, led by "vasopressors / ventilated in last
> 24h (risk)". Rankings move as the live replay advances, so don't rely on fixed
> IDs. The capped row is a strong trust moment — use it (see the line below).

**Tell.** "A list is only useful if a clinician can see *why*. Let's open one."

**Show.**
- **Top factors** in clinical language, each marked *supports* or *risk* (SHAP).
- **Lactate note** (when lactate is a top factor) — "the tool tells the clinician
  how to read one of its most influential features."
- **AI clinical summary** — plain-language paragraph from a Databricks-hosted
  foundation model (Llama 3.3 70B), generated from the factors only.
- **Care plan** — next check-in hours and monitoring thresholds tied to the
  factors (e.g., SpO₂ continuous, escalate < 92%).
- Vital-sign trends.

**Tell (business landing).**
> "This is what earns clinician trust: no black box, the reasons are on the
> screen, and the summary is something a nurse can read in fifteen seconds at
> handoff. Trust is what drives adoption, and adoption is what turns into bed-days."

**Show the guardrail (capped row, 30 s).**
> "This patient ranks near the top on GCS and labs — but they've been on
> vasopressors in the last 24 hours, so the tool will not call them Ready. It
> caps them at Borderline and puts the reason first. The model ranks; the
> clinical rules decide what's even eligible."

*Technical aside (only if the architect is leaning in, 20 s):* "The factors are
SHAP values from the served LightGBM model; known-risk features like ventilator
and vasopressors are forced to display as 'risk' whatever the SHAP sign; guardrail
rules inject risk factors for recent extubation, active bleeding and active life
support; and active life support in the last 24h caps the band — in the app and
in the pipeline's own scores, so Genie gives the same answer.
The narrative model only paraphrases those factors; it doesn't score anything."

### Segment C — Analytics (≈2 min) — *Analytics page*

**Tell.** "Now the view for leadership — is this working, and can we trust it?"

**Show.**
- Band distribution, LOS by band, feature importance (GCS, urine output and age
  lead — clinically intuitive drivers).
- **Model honesty card**: **AUC 0.89** headline, shown *next to* the
  **readmission-only AUC 0.63** and the **not-safe PR-AUC 0.78** (vs a 12% base
  rate). Say it before they ask: "the model is strong at flagging patients at risk
  of dying if we step them down; predicting readmission alone is still hard, and
  we show that on the screen."
- **Drift tile** (PSI / KS against the training baseline, checked daily).

> Note for the day: in a fresh environment the latest drift run may show verdict
> **"insufficient"** (no live scores in the last 24 h) with a large PSI number.
> Say: "the monitor correctly refuses to call drift on too little live data" —
> don't read the PSI value out loud.

**Tell (business landing).**
> "You get a weekly answer to two questions your board will ask: are we moving
> patients faster, and is the model still behaving the way it did when we
> validated it? Drift monitoring is the early warning before a model quietly
> goes stale."

### Segment D — Genie (≈2 min) — *Genie tab*

**Tell.** "Not everyone will open an app. Your ops managers ask questions."

**Show.** Ask: *"How many current ICU patients are ready for step-down?"* → show
the generated SQL → the answer.

> You are in `icu_micu`, so the answer is **scoped to MICU** (2026-10-12: 15
> patients — 5 Ready, 6 Borderline, 4 Not ready; it moves with the replay). The
> SQL reads `census_scores_governed` — scores the **pipeline** computed with the
> served model, not historical outcomes. Turn the scoping into the governance
> moment instead of hiding it:
> "Notice it answered for MICU only — I'm signed in as an MICU user. The same
> question from the SICU manager returns SICU. Access control lives in the data
> layer, so a new tool like Genie inherits it for free."

Optional second question: *"How many current patients are on vasopressors and a
ventilator at the same time?"*

**Tell (business landing).**
> "Self-service answers without a ticket to the analytics team — and without
> creating a second, ungoverned copy of patient data."

### Segment D2 — Live stream (≈1.5 min, optional) — *Jobs → `icu-live-vitals-replay` → Run now; then the app*

**Tell.** "You've asked whether this is a batch report or something the unit can
run on. Let me push the next hour of vitals in."

**Show.**
- Run the replay job once (or point at its 5-minute schedule if unpaused). It
  releases the next hour of the census patients' real charted vitals.
- Pipeline graph: the **continuous** pipeline picks them up — bronze in ~5 s,
  gold features and **pipeline-computed scores** in ~2 min.
- Refresh the app census ~3 min later: the ranking has moved (on 2026-10-12 the
  top patient changed between two releases).

**Tell (business landing).**
> "When a patient's vitals change at 3 a.m., the shortlist the day team opens at
> 7 a.m. already reflects it — no overnight batch, no one re-running a report."

*Technical aside:* "Bronze is streaming tables over the share's history; one
append flow is the history, a second is the live feed; silver and gold refresh
continuously, and the pipeline scores the census through the serving endpoint
with `ai_query`. In a pilot the feed is your ADT/charting extract instead of a
replay."

### Segment E — Platform underneath (≈1.5 min) — *slide 5, then slide 7*

**Tell.** "Ninety seconds on what's underneath, because it's what makes this
repeatable at your scale."

**Show (slide 5 flow).** Source → **Lakeflow** medallion, **continuously
streaming** (bronze → silver → gold) → **Unity Catalog** (lineage, DOB removed,
identifier masks, row-level access) → **Mosaic AI model serving** + foundation
model → **Lakebase** (Postgres, pseudonymised copies) for fast app reads →
**Genie** → **Databricks App**.

**Tell (both altitudes in one breath).**
> For the exec: "One platform, one copy of the data, one set of permissions —
> fewer vendors and fewer places for patient data to leak."
> For the architect: "Everything you saw deploys from code with Asset Bundles,
> and there's a test suite behind it — 198 backend, 37 frontend, 68 pipeline and
> ML unit tests, and 26 live integration tests that check things like 'no date of
> birth anywhere in silver or gold'. I re-stood this whole environment up from the
> repo this week."

---

## 4. Land the value and the ask (≈3 min) — *slide 4 + slide 9*

**Value math — do it with their numbers, not ours.** Ask for ICU beds, occupancy
and average LOS; if they won't give them, use this illustration and say so:

| Input | Illustration |
|---|---|
| ICU beds × occupancy × 365 | 30 × 85% × 365 ≈ **9,300 patient-days / year** |
| 10% LOS reduction | ≈ **930 patient-days** ≈ **2.5 beds** of new capacity |
| Value per avoided ICU day ($2–5k, deck range) | ≈ **$1.9M–$4.7M / year** |

> "For a 30-bed unit, ten percent is roughly two and a half beds you didn't have
> to build or staff. Whether you count that as cost avoided or as transfers and
> electives you can now say yes to depends on how full you are — and that's
> exactly what the pilot measures."

> ⚠ Slide 4's footnote says "0.8-day average LOS reduction". At a typical ICU LOS
> of 3–4 days that is 20–25% — above the 10–15% headline. Don't quote 0.8 days;
> use the table above, or fix the slide.

**The ask (slide 9).**
> To the business stakeholder: "Sponsor a 60–90 day pilot in one ICU. We score it
> on two numbers you already report: ICU length of stay, with the safe-transfer
> rate held or improved — 72-hour bounce-back not going up."
>
> To the technical stakeholder: "Point the same pipeline at an extract from your
> EHR. The architecture doesn't change; the bronze layer's source does."
>
> To both: "And we'd want your ICU medical director to co-own the readiness
> criteria from day one."

**Close.** "If that's a fair test, the next step is a 30-minute scoping session
with your ICU lead and your data team to pick the unit and the success metrics."

---

## 5. Objection handling

Pattern for every answer: **acknowledge → answer at the asker's altitude →
bridge to the other persona if useful → check ("does that address it?")**.

### From the business stakeholder

**"What does this cost?"**
> "Consumption-based — you pay for the pipeline, the serving endpoint and the
> app, not seats; the endpoint scales to zero when no one's using it. The one
> real dial is freshness: a continuously streaming pipeline runs around the clock,
> a 15-minute triggered refresh costs a fraction of that, and we'd pick it with
> your ICU team based on how fast the shortlist needs to move. For a one-unit
> pilot either is small next to the cost of one ICU day per week. I'd rather size
> it on your volumes than quote a number now." *(Don't make up a dollar figure.)*

**"How long before we see value?"**
> "The platform piece is already built — you watched me re-deploy it from code.
> The time goes into two things: getting a governed EHR extract landed, and your
> clinicians validating the index. Plan weeks for the first, and the 60–90 day
> pilot for the second. We measure LOS from the first full month."

**"What's the clinical risk? What if it's wrong?"**
> "It's designed as decision support, not a discharge gate: a relative rank, the
> reasons on screen, and the clinician makes the call. Known risks like
> ventilator and pressors are always shown as risks. And the pilot success
> criteria include the safe-transfer rate — if bounce-backs go up, the pilot has
> failed, full stop."

**"How good is the model?" / "0.89 sounds too good."**
> "0.89 is the headline — the model separates patients who step down safely
> from those who are readmitted or die within 72 hours. Two honest caveats, and
> they're on the screen: most of that comes from defining the outcome correctly —
> our first version counted patients who died as successful step-downs, and fixing
> that took us from 0.66 to about 0.86 on its own. And on readmission alone it's
> 0.63 — bounce-backs are genuinely hard to predict. So it's strongest at the
> thing you'd least want to get wrong: flagging who is too sick to move. That's
> also why we show a rank, not a probability, and why the pilot validates it
> prospectively with your clinicians."
> *Technical bridge:* "Held-out test, touched once. Not-safe PR-AUC 0.78 against
> a 12% base rate; precision 0.63, recall 0.73. The 0.86 is the old 30 features on
> the corrected label — that isolates the label fix from the 23 new features. We
> also closed a lactate leak (it used post-ICU results) and took the 40 census
> patients out of training, so their scores are out-of-sample."

**"Why does a ventilated patient have a high index?"** *(if they spot one)*
> "Because the index is a rank on everything else — oxygenation, GCS, labs. But
> look at the band: anyone on vasopressors or a ventilator in the last 24 hours is
> capped at Borderline and the reason is listed first. We found that case in
> testing and made it a hard rule rather than trusting the model to learn it.
> Your ICU director would own that rule set."
> *If they spot 'on ventilator' without a cap:* "That flag means *at some point in
> the stay*; the cap uses support active in the last 24 hours, which is the
> clinically relevant window."

**"Will clinicians actually use it?"**
> "Only if it saves them time on rounds and they trust the reasons — that's why
> the explanation and the one-paragraph summary are on the patient view. We'd
> track adoption in the pilot: how often the census is opened on rounds."

**"We have Epic. Why not just use what's in the EHR?"**
> "Keep the EHR as the system of record and the place clinicians work. This sits
> beside it: it uses data the EHR already captures, adds a model you govern and
> can tune, and the same data serves ops, analytics and AI without a new copy per
> use case. Surfacing the index back inside the clinician workflow is a pilot
> design question we'd answer with your informatics team."

**"Who's liable if a step-down goes wrong?"**
> "The clinician makes the decision, the same as today; the tool doesn't write
> orders. Your clinical governance committee would approve the pilot protocol —
> that's normal for decision support."

### From the technical stakeholder

**"Walk me through the architecture."**
> Source (Delta Sharing today; your EHR extract tomorrow) → Lakeflow declarative
> pipeline running **continuously** on serverless — bronze is streaming tables
> over the share's history plus a live feed; silver and gold are materialized
> views it keeps current, and the pipeline scores the census through the serving
> endpoint with `ai_query` → Unity Catalog governs every layer (DOB dropped,
> identifier masks, row-level access) → LightGBM trained in MLflow by a bundle
> job, registered in UC (`readiness_model` v6), served on Mosaic AI with a
> SHAP-explaining pyfunc → pseudonymised gold copies synced to Lakebase Postgres
> for millisecond app reads → FastAPI + React Databricks App → Genie on the
> governed views → a daily job computes PSI/KS drift. All deployed with Asset
> Bundles.

**"How do we integrate with our EHR?"**
> "Only bronze changes. Land your Clarity/Caboodle extract or HL7/FHIR feed in
> cloud storage or via Lakeflow Connect, map it to the same silver contract —
> stays, vitals, labs, meds, ventilation — and everything downstream is
> unchanged. Feeding the result back into the EHR — a column, a flag, an in-basket
> message — goes through your integration engine and we'd scope it with you."

**"Security, PHI, HIPAA?" / "Show me the PII is protected."**
> "Three layers, and the pipeline enforces them rather than a reviewer. Date of
> birth is used once to compute age and then dropped — age is whole years, capped
> at 90 per HIPAA Safe Harbor, and a pipeline expectation fails the run if that's
> ever violated. A small audit table in the pipeline fails it if a date-of-birth
> column ever appears in the curated layers. Patient and admission IDs carry Unity
> Catalog column masks — raw only for an admin group, a stable pseudonym for
> everyone else — and the copy the app reads stores only pseudonyms, so the
> operational database never holds a raw identifier."
> *Show if asked:* `evidence/pii-obfuscation.txt` — the event log shows every
> PII expectation passing on 61,532 rows with 0 failures; Postgres: 0 raw IDs.
> *Be precise:* the pseudonym is a salted hash in the function — display
> masking, not cryptographic de-identification; production keys it with a secret.
> "Data stays in your cloud account under Unity Catalog. Identifiers carry PII
> classification tags; access is least-privilege. Care-unit access is enforced in
> the data layer through governed views — you saw Genie scope to MICU — and the
> app has a fail-closed per-unit check that denies everything when a user's unit
> can't be determined. Users act under their own identity; the app's service
> principal only gets SELECT on the tables it needs. For production we'd run in a
> HIPAA-eligible configuration under your BAA. The GenAI summary runs on a
> Databricks-hosted model, so prompts don't leave the platform."
> *Be precise if pushed:* the app-side unit check is built and tested but
> **config-gated, off by default** in this deployment.

**"How good is the data? MIMIC isn't our data."**
> "Agreed — MIMIC is a proxy. The pipeline handles what you'd also see in an EHR:
> outlier capping on vitals, unit normalisation, and two charting systems
> (CareVue and MetaVision) reconciled into one vitals model. About 3,200 very
> short stays have no vitals; the model handles missing values explicitly rather
> than imputing zeros. The label is 'left the ICU alive, not readmitted and not
> dead within 72 hours' — and I'll be candid that our first version missed the
> 'alive' part, which is exactly the kind of thing your clinicians should
> challenge. Every feature is taken from before the step-down point; we found and
> closed one leak where lab values after discharge crept in."

**"How do you know it isn't drifting?"**
> "A daily job compares live scores to the training baseline with PSI and KS and
> writes the result to a governed table the app shows. It fails loudly on an
> empty baseline or a model-version mismatch, and it says 'insufficient' instead
> of guessing when there's too little live data."

**"Why Lakebase and not just query the warehouse?"**
> "The app needs sub-second, high-concurrency point reads per click — that's an
> OLTP pattern. Lakebase is managed Postgres, kept in sync from the gold tables,
> so the analytics and the app read the same governed numbers without us writing
> sync code."

**"What about model governance and rollback?"**
> "Models are versioned in Unity Catalog with lineage back to the training table;
> serving pins a version (v6 today), so rollback is a config change. Training is
> a bundle job: three-way split, test touched once, rows sorted first so the
> split is reproducible, and an explicit input schema so one missing lab can't
> fail a whole census call. Every change to the feature list is checked by a test
> across the four places it lives."

**"Lock-in?"**
> "The data is Delta, the model is MLflow with LightGBM, the app is FastAPI and
> React, and Lakebase is Postgres — all open formats and standard tooling."

**"Is the 'current census' real-time?"**
> "Yes — the pipeline runs continuously. Because MIMIC is historical, we hold back
> the census patients' last day of real vitals and replay it in time order; new
> readings land in bronze within seconds and the scores update within about two
> minutes (you saw it in Segment D2). In the pilot the feed is your ADT and
> charting stream instead of a replay — same pipeline, same latency profile."
> *If pushed on the app lag:* "The app reads a Postgres snapshot refreshed after
> each release, so it trails the pipeline by one release — minutes, not hours.

### Switching altitude mid-answer — the move to practise

When the architect asks something deep, answer in two layers and hand back:
> "…so the row filter is a UC SQL function evaluated per query against group
> membership. *[turn to the exec]* What that means for you: a new analytics tool
> can't accidentally show the SICU team MICU patients — permissions travel with
> the data, not the app."

When the exec asks something the architect will want to probe, give the outcome,
then invite:
> "…yes, the same pipeline works on your data. *[to the architect]* Happy to go
> deeper on how the EHR mapping works if that's useful."

---

## 6. Do / don't

- **Do** say "relative readiness index" / "rank". **Don't** say "probability of
  safe discharge" or "the model predicts they're safe".
- **Do** say "decision support"; **don't** imply automation of discharge orders.
- **Do** volunteer the AUC caveats (readmission-only 0.63; the label fix) and the
  MIMIC/replayed census before you're asked.
- **Don't** quote clinical outcome results — none exist yet; the pilot creates them.
- **Don't** invent pricing; offer to size it.
- **Do** end each demo segment with a one-sentence business "so what".

## 7. Numbers to have ready

| Fact | Value | Source |
|---|---|---|
| ICU stays | 61,532 (training: 61,492 — the 40 census stays excluded) | `evidence/05-ml-metrics.md` |
| Label balance (v6) | 54,195 safe / 7,297 not safe (11.9%): 5,521 deaths, 1,766 bounce-backs | `evidence/05-ml-metrics.md` |
| v2 label defect | 5,274 deaths had been labelled "safe" | `evidence/05-ml-metrics.md` |
| Test AUC (v6) | **0.891** (v2 0.659; v2 features + fixed label 0.863) | `evidence/05-ml-metrics.md` |
| Readmission-only AUC | 0.635 | `evidence/05-ml-metrics.md` |
| Not-safe PR-AUC / precision / recall | 0.776 / 0.63 / 0.73 (base rate 11.9%) | `evidence/05-ml-metrics.md` |
| Features | 53 (v2: 30) — top: GCS, urine output, age | `evidence/05-ml-metrics.md` |
| PII | DOB dropped; age capped 90; 0 expectation failures; 0 raw IDs in Postgres | `evidence/pii-obfuscation.txt` |
| Streaming latency | bronze ~5 s · gold + scores ~2 min · Lakebase ~40 s | `evidence/streaming-run.txt` |
| Demo census | 40 stays; MICU 15 · SICU 10 · CCU 15 (synthetic units) | `evidence/care-unit-distribution.txt` |
| Tests | 198 backend · 37 frontend · 68 unit · 26 live integration | `evidence/test-run.log` |
| Narrative model | `databricks-meta-llama-3-3-70b-instruct` | `src/genai/narrative.py` |
| Target outcome | 10–15% ICU LOS reduction; $2–5k per avoided ICU day | deck slide 4 |

---

> **Resolved 2026-10-12:** the life-support guardrail (vasopressors / ventilation
> active in the last 24h → band capped at Borderline, risk factor injected) now
> makes "known risks always shown as risks" true — app, pipeline scores and Genie.
>
> **Cost:** the pipeline is continuous and runs 24/7 — stop it between rehearsals
> (`databricks pipelines stop 9d6181f7-d1bb-48ba-8501-3126ff309c70 --profile icu-sandbox`)
> and start it ~15 min before the session.
