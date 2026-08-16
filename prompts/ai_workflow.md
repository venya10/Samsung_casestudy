# AI prompts and workflow

The brief asks for "AI prompts or workflows" as a deliverable. This is the honest
account of where AI is used in the product, how, and where it is deliberately not.

---

## 1. Where AI sits

```
data/raw/  ──▶ ingest ──▶ model ──▶ insights ──▶ alerts
  (1 file)     cleaning   facts     efficiency   rules engine
                            │           │            │
                            └───────────┴────────────┘
                                        │
                             DuckDB (marketing.duckdb)
                                        │
                          ┌─────────────┴─────────────┐
                     static site                 assistant.py
                      (charts)              (Gemini + SQL tools)
```

**Every number is computed by Python or SQL. The model never produces a figure.**
That boundary is the most important design decision in the project.

### What AI does not do

| Task | Why not |
|---|---|
| Cleaning, typing, reshaping | Must be deterministic and identical on every run. A model that "mostly" parses correctly is worse than useless. |
| Computing KPIs | Arithmetic belongs in code. Every KPI has one definition, in `model.py`. |
| The panel model | Ordinary least squares with cluster-robust errors. Reproducible and inspectable. |
| Evaluating alert rules | A rules engine over `config/rules.yaml`. A marketing manager must be able to change a threshold without asking anyone to re-prompt a model. |

### What AI does

Answering ad-hoc questions; translating findings into business language; and — the
part that matters most here — **declining questions this dataset cannot answer.**

---

## 2. Why tool use, not RAG

The obvious build is to embed the CSV and retrieve chunks. **That is the wrong
architecture for tabular data**, because it makes the model read numbers out of
retrieved text — precisely the operation language models are least reliable at.

The tool-use design inverts it. The model's job is to turn a business question into
SQL and explain the rows it is handed. DuckDB does every calculation. Bad SQL
errors, and the model can see the error and correct itself; it cannot quietly
produce a plausible wrong number.

**The test that separates them:** ask *"what was blended CPA in the last four
weeks?"* The tool-use assistant writes `SUM(spend)/SUM(conversions)`. A RAG system
averages the weekly CPA values — a different and wrong number, because an average of
ratios is not the ratio of sums.

---

## 3. The tools

| Tool | Purpose |
|---|---|
| `run_sql` | Read-only DuckDB. The workhorse. |
| `describe_schema` | Tables and columns, so the model can orient before writing SQL. |
| `get_alerts` | The early-warning feed with owners and actions. |
| `get_analysis` | Channel efficiency, market scorecard, panel model, products, reallocation — in one call. |

`run_sql` alone would technically cover everything. `get_analysis` exists because
the pre-computed tables **carry the caveats**: they blank ROI where a channel has no
attribution, rather than returning the zero that raw SQL over the facts would give.
A model querying `fact_channel` directly could compute "TV ROAS = 0" and report it.
The analysis table returns null and says why.

### Guardrails

1. The DuckDB connection is opened **read-only**.
2. Only `SELECT` and `WITH` pass validation; rejections return a message the model
   can act on.
3. One statement per call.
4. Results row-capped at 200 with a note telling the model to aggregate.
5. The agentic loop stops after 12 tool rounds.
6. `stop_reason` is checked **before** reading content, so a refusal cannot be
   mistaken for an empty answer.

---

## 4. The system prompt

Full text: [`system_prompt.md`](system_prompt.md). Its most important section is not
the KPI definitions — it is **what this dataset cannot answer**:

> **Eight weeks. There is no marketing mix model, and there cannot be.** […] If
> asked for channel contribution, incrementality, adstock, saturation, or "what
> would happen if we cut channel X" — say plainly that this data cannot support it
> and explain why. Do not substitute observed ROAS and call it contribution.
>
> **TV has spend but no attributed sales.** […] Never quote a TV ROI, ROAS, CPA or
> efficiency index — it does not exist.
>
> **Brand metrics are indicative, not measured.** […] Compare markets; never
> attribute a week-to-week brand movement to a change in spend.

An assistant that answers every question is a liability on a dataset with hard
limits. Encoding the limits is what makes it usable in a room with a director.

The schema block is **generated from the live database** at call time and appended
to the static prompt. A hand-maintained schema drifts the moment anyone adds a
column, and the failure is silent — the model writes confident SQL against columns
that no longer exist.

---

## 5. Where AI was used to build this

| Used for | Notes |
|---|---|
| Writing the pipeline, dashboard and assistant | Reviewed and tested; `validate_site.py` and the data quality log exist because generated code needs verifying, not trusting |
| Interrogating the dataset before designing | The checks in §6 came from asking "what would make this analysis wrong?" |
| Drafting explanatory copy | Every business claim re-checked against computed output |
| **Not** used for | The modelling approach, the decision to drop the MMM, the treatment of unmeasured channels, or the KPI definitions. Those are judgement calls that have to be defensible in a room. |

### The highest-value use: adversarial review

The most useful AI-assisted step was asking a model to attack the analysis rather
than produce it. Findings that came out of that, all now guarded in code:

**On the synthetic build** (kept in `archive/`, and the reason the MMM was dropped
rather than never attempted):

- A mix model claiming media drove **69% of sales volume** — commercially absurd,
  and it looked fine in a table. Caused by measuring contribution against *zero*
  spend when the data contains no zero-spend weeks.
- **Channel contributions summing to more than total sales** — unbounded market
  dummies going negative so collinear media coefficients could inflate.
- **Five of eight channels estimated at exactly zero** — non-negative least squares
  collapsing under collinearity, an artefact rather than a finding.
- **ROI of 120x on low-variance channels** — the numerator floored in transformed
  space while the denominator was floored in dirhams. Two different counterfactuals
  silently compared.

**On the real data:**

- **TV having spend but no sales** — caught by a structural-sparsity assertion that
  compares actual coverage against the documented model, not by reading the file.
- **Brand metrics varying 39 points inside a market-week** — caught by testing
  whether they were constant within each candidate grain.
- **An alert firing on sentiment 0.85 vs a peer median of 0.86** — statistically
  −2.1 SD, practically meaningless. Fixed with a practical-significance floor; it
  was generating eight noise alerts per cycle.
- **Website scored "below breakeven"** when it has no spend at all — `NaN >= 1.0`
  is `False`, so it fell through to the failure branch. A channel that was never
  measured was being scored as one that failed.

Every one of these produced a confident, plausible-looking number. None would have
been caught by checking that the code ran.

---

## 6. Reproducing

```bash
export GEMINI_API_KEY=...               # or put it in .env -- free key, no billing,
                                         # from https://aistudio.google.com/apikey
python src/assistant.py                 # runs the brief's questions in the terminal
python src/serve.py                     # dashboard + live assistant
```

Without a key, `assistant.py` falls back to a deterministic responder over the same
tables and says clearly that it is doing so. A demo should never dead-end on a
missing key.

Model: `gemini-flash-lite-latest` — the full flash tier's free quota is a mere 20
requests/day/project, exhausted almost immediately in real use; the lite tier's is
far more generous and plenty capable for this task. Every answer in the dashboard
expands to show the exact tool calls and SQL behind it — an answer you cannot audit
is not usable for a budget decision.
