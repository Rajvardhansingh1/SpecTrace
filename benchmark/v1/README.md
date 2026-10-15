# SpecTrace benchmark, dataset v1

14 synthetic cases. Each case has two versions of a small API spec (`a/`, `b/`) and an `expected.json` with the changes and impacts a careful reader would report. No third-party content.

Run it from `backend/`:

```
conda run -n SpecTrace python -m scripts.benchmark            # all cases
conda run -n SpecTrace python -m scripts.benchmark --split heldout --details
conda run -n SpecTrace python -m scripts.benchmark --save     # writes results/<date>-<split>.json
```

## How the labels were produced

- The cases and labels were written by the AI assistant that built the engine, **before** the first benchmark run, from the question "which entities would a reader have to re-check when this one changes?". Nobody else has reviewed them yet. Treat the numbers as a development measurement, not an independent evaluation.
- A citation is the line where the impacted entity makes its reference (`$ref`, an endpoint mention, a backticked name, a JSON example fence, an anchor link). Line numbers were found by locating the quoted text in the file; the quoted text is stored in `expected.json` (`cite.text`) so a reviewer can check it. Removed entities cite version A, everything else version B.
- `certainty` is `confirmed` when an explicit, checkable reference chain exists (`$ref`, `METHOD /path` that matches an endpoint, anchor link, requirement ID) and `inferred` when the link is a guess (a backticked schema name, JSON keys that match a schema).
- Splits: `dev` (c01-c06, c13) may be used while changing the engine. `heldout` (c07-c12, c14) must not be used for tuning; look at it only to report results.
- c04 is deliberately hard: the documentation section is four hops from the change and the engine searches three. It is labeled as impacted because it is.
- c06 is deliberately adversarial for keyword search: the docs use the everyday word "item" and an unused schema is called `Item`.

## Metrics

All counts are summed over cases, then divided (micro-average). An impact is the pair (changed entity, impacted entity).

| Metric | Definition |
|---|---|
| Impact precision | reported pairs that are in the labels / reported pairs |
| Impact recall | labeled pairs that were reported / labeled pairs |
| Certainty accuracy | among correctly found pairs, the share with the right `confirmed` or `inferred` label |
| False-confirmed | reported `confirmed` pairs whose label is `inferred` or absent. Must be 0 for the product claim "confirmed means confirmed" |
| Citation accuracy | among correctly found pairs, the share whose cited file and line equal the label |
| Change detection | precision and recall of the set of changed entity keys; classification accuracy among those matched |
| Unsupported-impact rate | reported impacts that lack a valid evidence path (empty path, path not chained from the impacted entity to the change, evidence outside the file, or `confirmed` with an inferred edge) / reported impacts. Must be 0 |
| ms per document | analysis time divided by files in both versions; median and max over cases |

Precision is `n/a` when nothing is reported.

## Baseline

Keyword retrieval: for each changed or removed entity, every other entity whose text contains the entity's name as a whole word, ignoring case. It has no certainty label and no citation line, so only precision and recall are reported for it.

The baseline's pattern was corrected once after the first run: it initially refused a name preceded by `/`, so `schemas/Pet` did not count as a mention of `Pet`. That handicapped the baseline unfairly. The engine was not changed.

## Results

Stored under `results/` with the dataset version, engine configuration, commit and date. Results from different dataset versions are not comparable.

## Known limits of this dataset

Small (14 cases, 26 labeled impacts), synthetic, single labeler, OpenAPI 3 `components/schemas` references only, English prose. The held-out split has 10 labeled impacts, so one error moves its recall by 10 points.
