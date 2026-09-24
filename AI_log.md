# AI Usage Log

## Tools used

- Claude (Anthropic), through the claude.ai chat interface.
- No other AI tools were used.

## Summary

I relied heavily on Claude for this assessment. Claude wrote most of the code in the
submission, including the schema validator, the spatial join, the feature comparison,
the pipeline entry point and the performance changes.
My role was to specify requirements, supply the data and error output, run everything,
verify results against the reference data, and make the final decisions listed below.
All results quoted in the README and this log come from my own runs. I have not
independently re-implemented the code Claude wrote, and I want to be clear about that.

## Session: GeoJSON Schema Validation & H3 Hex Join

**Date:** 2026-09-23/24
**Tool used:** Claude (Anthropic)

### Task 1: GeoJSON schema validation & conformance scoring
- Claude drafted the JSON Schema for the `city-hex-polygons-8` structure
  (FeatureCollection, feature properties, Polygon geometry).
- I ran it and reported failures. Claude diagnosed and fixed them (a missing
  `resolution` property, and a `$ref` merge bug that leaked top-level keys into
  per-feature validation and masked real errors).
- Claude designed and implemented the weighted conformance score and the external
  `conformance_config.json`, and the tolerance-based polygon comparison (rounding,
  ring closure, winding/start-vertex invariance).

### Task 2: Service request to H3 hexagon join
- Claude wrote the geopandas point-in-polygon `sjoin` against the hex polygons, the
  rule that missing coordinates get `h3_level8_index = 0`, the join-failure logging,
  the `JoinThresholdExceededError`, and the `timed_step` timing wrapper.
- Claude helped debug environment and data issues that I hit and reported: wrong
  relative paths, a `.url` shortcut being read as a filename, wrong assumed
  columns/delimiter, and the role of `sr_hex.csv.gz` as both input and reference.
- Claude explained the ~77% apparent match rate as a representation mismatch
  (my `0` vs. blank/NaN in the reference). I confirmed the true join failure rate
  was 0.0004% (3 of 729,270 coordinate-bearing requests).


## Log of AI assistance (final session)

| # | Area | What Claude did | What I did / how it was verified |
|---|---|---|---|
| 1 | Spatial join (`assign_hex_index`) | Wrote the function and advised on `within` vs `intersects`, dtype and row order after `concat`, and justifying the threshold from a measured baseline. | Ran the `within` vs `intersects` comparison on the full dataset: identical results, 0 duplicate matches. Measured the baseline failure rate (3 of 729,270). |
| 2 | Feature comparison (`compare_features.py`) | Wrote and revised the script, including duplicate-index warning, missing-geometry handling and logging. | Ran it: 3,832 of 3,832 hexagons match. The data has no duplicates or missing geometries, so those guards were not triggered. |
| 3 | Schema validation (`validate_schema.py`) | Wrote the validator, then found and fixed weighting bugs (unweighted missing properties, `feature.type` key never matching, one rule charged several times per feature, an unused variable). | Ran it: score 1.0000 (PASS), 0 of 30,656 weight failed. **Not tested with invalid data**, so the failure paths have not been exercised. |
| 4 | `main.py` | Wrote it and later fixed a `NameError`, a duplicate validation call, a missing `compare_features` call and hardcoded values. | Ran the pipeline end to end. |
| 5 | Performance | Proposed and wrote the load-once change and the `hex_gdf_from_features` / `validate_against_reference_df` helpers. | Applied them and measured: about 27.4 s to about 19.1 s, results unchanged. The service request load (about 12.6 s) is still the largest step. |
| 6 | Reference mismatches | Suggested the `h3.latlng_to_cell` diagnostic and interpreted the results. | Ran the check: the library equals the reference on 29 of 29 mismatched rows and equals my join on 0 of 29. The 3 unmatched rows' reference hexagons are not in the polygon file. `h3` is a diagnostic only, not part of the pipeline. |
| 7 | README | Drafted the structure and wording and updated it as I supplied results. | Filled in values from my own runs and checked the README against the code. |
| 8 | Requirements | Explained how to build `requirements.txt` and test it in a fresh environment. | Compiled the file and ran the fresh-environment test. |
| 9 | Git | Gave commands to remove the virtual environment from the repo and history and fix the commit history. | Ran them myself. |

## Errors made by the AI, and how they were caught

- **Credentials:** the first README draft told the runner to set AWS credentials as
  environment variables. After seeing `aws_client.py`, it was corrected to match
  the code, which fetches credentials from the URL supplied with the challenge.
- **Timing estimate:** Claude predicted about 12 s after the loading change. The
  measured time was about 19 s, and the README uses the measured figure.

## What I contributed

- Requirements, data, and the error output that drove each fix
- Running and verifying every step, including the `within` vs `intersects` check,
  the baseline measurement and the 29-row diagnostic
- Final decisions: the 1% join error threshold (based on the measured 0.0004%
  baseline), the 0.98 / 0.90 conformance thresholds, keeping the spatial join
  rather than computing indices with H3 directly, documenting the 29 mismatches
  rather than hiding them, and fetching AWS credentials within the code

## Limitations

- Most of the code was written by Claude rather than by me, so my understanding
  comes from reviewing and running it, not from having authored it line by line.
