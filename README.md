# Cape Town H3 Data Pipeline
 
This project has two parts:
 
1. **Data extraction and validation:** read the H3 resolution 8 hexagons for the City of Cape Town out of a multi-resolution GeoJSON in S3 using S3 Select, validate them against a reference file, and score them against a documented schema.
2. **Data transformation:** assign each service request to the resolution 8 hexagon that contains it, validate the result against a reference output, and fail loudly if too many requests cannot be joined.
Every stage logs its execution time.
 
## Quick start
 
```bash
pip install -r requirements.txt
python3 main.py
```
 
`main.py` runs both parts in order.
 
### Requirements
 
- Python 3.10.12
- Dependencies are listed in `requirements.txt` (including `boto3`, `pandas`, `geopandas`, `shapely`)
- AWS credentials with read access to the source bucket. Credentials are read from environment variables and are never stored in the repository.
### Input files
 
| File | Purpose |
|---|---|
| `city-hex-polygons-8-10.geojson` (S3) | Source of H3 polygons and index values for resolutions 8, 9 and 10 |
| `city-hex-polygons-8.geojson` | Reference file for validating the extracted resolution 8 hexagons, and the hexagon layer used in the join |
| `sr_hex.csv.gz` | Reference output for validating the service request join |
| Service request dataset | The requests to be assigned to hexagons |
| `schema.json` | The expected schema used to compute the conformance score |
 
## Part 1: Data extraction and validation
 
### Extraction
 
The resolution 8 hexagons are read from `city-hex-polygons-8-10.geojson` using **S3 Select**. The query iterates over the GeoJSON `features` array and filters on `properties.resolution`, so the filtering happens on the S3 side and only the matching features are transferred. The resolution is a parameter of `extract_data_from_s3` and defaults to 8.
 
### Validation against the reference file
 
The extracted features are compared with `city-hex-polygons-8.geojson`, matched on `properties.index`. For each hexagon in both sets, the script checks the centroid latitude and longitude (within a tolerance of 1e-9) and the polygon geometry. Geometry is compared after rounding coordinates to 7 decimal places, and ignoring the starting vertex, the winding direction and the repeated closing point, since none of these change the shape. Duplicate indices and features with missing geometry are reported rather than silently ignored.
 
The result reports the match rate (exact matches as a fraction of the reference hexagons), the indices missing from or extra in the extracted data, and any field-level mismatches. The match rate is measured against the reference, so it does not penalise extra hexagons; extras are reported separately and should be checked alongside the rate.
 
### Schema conformance score
 
The expected schema is defined in `schema.json`, and the scoring weights and thresholds are defined in `conformance_config.json`. Both are kept separate from the code, so they can be reviewed and changed without touching the script.
 
- **Score:** a weighted pass ratio, calculated as `1 - (sum of failed rule weights / sum of all rule weights evaluated)`. A score of 1.0 means every rule passed. The score is calculated across the whole dataset: every feature is checked against all seven rules, the weights of the rules that fail are summed, and that total is divided by the total weight of all rules across all features.
- **Checks and weights:**
  | Rule | Weight |
  |---|---|
  | `feature.type` | 1.0 |
  | `properties.index` | 1.5 |
  | `properties.centroid_lat` | 1.0 |
  | `properties.centroid_lon` | 1.0 |
  | `properties.resolution` | 1.0 |
  | `geometry.type` | 1.0 |
  | `geometry.coordinates` | 1.5 |
  The hexagon index and the polygon coordinates carry the highest weight, since they identify and locate each hexagon. Any rule without an explicit weight defaults to 1.0.
- **Thresholds:** the result is graded rather than pass/fail.
  | Score | Result |
  |---|---|
  | 0.98 or above | PASS |
  | 0.90 to below 0.98 | WARN |
  | below 0.90 | FAIL |

  The thresholds are chosen so that scattered record-level errors and systematic schema breakage are treated differently. Because the score is pooled across the dataset, a single rule failing on every feature costs 12.5% to 18.75% of the total weight, which always scores below 0.90 (FAIL). A score of 0.98 or above (PASS) allows up to 2% of the total weight to fail, and 0.90 to 0.98 (WARN) marks data that is usable but should be inspected. Whenever any feature is invalid, the number of invalid features is logged regardless of the label.

### Timing
 
The time taken by extraction and by each validation step is logged. Timing for each step is logged to the console.
 
## Part 2: Assigning service requests to hexagons
 
Each service request is assigned to the H3 resolution 8 hexagon that contains its latitude/longitude, stored in `h3_level8_index`. The join is a spatial join (`geopandas.sjoin`, predicate `within`), which uses a spatial index for speed.
 
### Handling of edge cases
 
- **Missing coordinates:** requests with an empty `Latitude` or `Longitude` are assigned index `0`, as specified. They are not counted as join failures, because they were never expected to match. Their number is logged.
- **Unmatched coordinates:** requests that have coordinates but fall in no hexagon are counted as join failures. They hold no index value (null) in the output.
- **Boundary points:** a point lying exactly on a shared edge could in principle match more than one hexagon. If this happens the first match is kept and a warning is logged. The `within` and `intersects` predicates were compared on the full dataset and gave identical results, with 0 boundary duplicates, so `within` is used.

### Join error threshold
 
The script raises `JoinThresholdExceededError` if the failure rate exceeds **1%** (the failed joins as a fraction of requests that have coordinates).
 
**Why 1%:** running the join on the full dataset gives a baseline failure rate of about 0.0004% (3 of 729,270 requests with coordinates fail to match any hexagon). The threshold sits well above that baseline, so ordinary noise in the data will never trip it, but it is far below what a systematic problem would produce. Swapped latitude and longitude, a wrong coordinate reference system, or a truncated hexagon file would each push the failure rate up to tens of percent or higher, and the script would stop instead of writing a badly joined dataset.
 
The threshold is a parameter of `assign_hex_index(sr_df, hex_gdf, error_threshold=...)`.
 
### Validation against the reference output
 
The output is compared to `sr_hex.csv.gz`. Only requests that have coordinates are compared, on the hexagon index. Of the 729,270 rows compared, 29 differ from the reference (a 99.996% match): 3 have no hexagon in the computed output, and 26 are assigned a different hexagon from the reference. The reference file holds `0` for all 212,364 rows with missing coordinates, matching the specification. The 29 mismatches were investigated using the H3 library (`h3.latlng_to_cell` at resolution 8). For all 29 rows the library's result equals the reference, and for none of them does it equal the join's result, so the reference index appears to have been computed directly from the coordinates with H3. The 26 rows assigned a different hexagon are most likely points close to a hexagon boundary, where testing against the polygon file's edges can disagree with H3's own cell boundaries. The 3 rows with no match are assigned by the reference to hexagons that are not in `city-hex-polygons-8.geojson`, so a join against that file cannot assign them. This is also why they make up the baseline failure rate above.

### Logging
 
Each run logs:
 
- the number of requests with coordinates, the number that failed to join and the failure rate
- the number of requests with missing coordinates
- the number of boundary duplicates
- the time taken by each stage
## Design decisions and trade-offs
 
- **S3 Select for extraction:** filters on the server side, which reduces data transfer and memory use compared with downloading and parsing the whole file.
- **Spatial join with an index:** avoids comparing every point against every hexagon.
- **Schema kept outside the code:** the conformance rules can be reviewed and changed independently of the script.
- **Failure rate measured against requests with coordinates only:** requests with no coordinates are expected not to join, so counting them would hide the real join quality.
- **Load each input once:** the hexagon layer for the join is built from the features already downloaded for the comparison, and the service request file is read once and reused for validation. This cut the total run time from about 27 s to about 19 s, almost all of it from no longer reading the service request file a second time.

## Limitations and possible improvements
 
- The spatial join reproduces the reference for all but 29 of 729,270 rows with coordinates (0.004%). Computing the index directly from the coordinates with the H3 library matches the reference on all 29 of those rows and would also be faster than a spatial join. The join was kept because the task asks for requests to be joined to the hexagon polygons, and it is what makes an unmatched request detectable and reportable against the city's hexagon set.
