# Demo recording

> **ACTION REQUIRED (submitter):** paste your demo recording link below. A short
> (2–5 min) walkthrough of the running app — ranked census, a patient detail with
> factors + AI narrative + care plan, the analytics/drift view — plus a Genie
> question or two, satisfies the "recording link" submission requirement.

**Recording link:** _<add Loom / Google Drive / YouTube-unlisted link here>_

## What the recording should show (script)

1. **Ranked census** — patients color-banded Ready / Borderline / Not-ready by the relative readiness index.
2. **Patient detail** — the top factors (with a known-risk like ventilator shown as *risk*), vital-sign trends, and the plain-language AI clinical summary + care plan.
3. **Analytics** — band distribution, LOS by band, and the model-drift tile (PSI/KS).
4. **Genie** — ask *"How many current ICU patients are ready for step-down?"* and show the generated SQL + answer.

Live app URL: https://icu-step-down-7474645692590282.aws.databricksapps.com

Static readable evidence of each of these is committed in [`../logs/`](../logs/),
[`../EVIDENCE.md`](../EVIDENCE.md), and [`raw/`](raw/); app screenshots are in
this folder (`screenshot-census.png`, `screenshot-analytics.png`,
`screenshot-patient-detail.png`) — note the repo collector excludes binary
images, so also attach the screenshots (and the deck PDF) directly in the
submission.
