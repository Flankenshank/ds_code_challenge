from pathlib import Path

from extract import s3client, extract_data_from_s3, load_reference_data
from validate_schema import validate_geojson
from compare_features import compare_features
from timing import timed_step, logger
from data_transformation import (
    load_service_requests, assign_hex_index, validate_against_reference_df,
    JoinThresholdExceededError, read_url_from_file, hex_gdf_from_features
)

BASE_DIR = Path(__file__).resolve().parent

bucket = "cct-ds-code-challenge-input-data"
region = "af-south-1"
source_file = "city-hex-polygons-8-10.geojson"
comparison_file = "city-hex-polygons-8.geojson"
schema_path = BASE_DIR.parent / "schema.json"
config_path = BASE_DIR / "conformance_config.json"
sr_url_file = BASE_DIR.parent / "data" / "sr_hex.csv.gz.url"

# Fraction of requests with coordinates that may fail to join. See README.
JOIN_ERROR_THRESHOLD = 0.01


if __name__ == "__main__":
    client = s3client()

    # ---- Part 1: extraction and validation ----
    with timed_step("S3 extraction"):
        logger.info("Extracting data from S3...")
        parsed_records = extract_data_from_s3(client, bucket, source_file)
        comparison_data = load_reference_data(client, bucket, comparison_file)
        logger.info(
            f"Records downloaded -> Extracted: {len(parsed_records)}, "
            f"Reference: {len(comparison_data)}"
        )

    with timed_step("Comparison with reference file"):
        comparison_result = compare_features(parsed_records, comparison_data)

    with timed_step("Schema validation"):
        schema_result = validate_geojson(parsed_records, schema_path, config_path)

    if schema_result["invalid_features"] > 0:
        logger.warning(
            f"{schema_result['invalid_features']} of {schema_result['total_features']} "
            f"features failed one or more checks "
            f"(score {schema_result['score']:.4f}, {schema_result['label']})."
        )
    else:
        logger.info(
            f"All features passed schema validation "
            f"(score {schema_result['score']:.4f}, {schema_result['label']})."
        )

    # ---- Part 2: join service requests to hexagons ----
    with timed_step("Load service requests"):
        hex_gdf = hex_gdf_from_features(comparison_data)
        sr_url = read_url_from_file(sr_url_file)
        sr_df = load_service_requests(sr_url)

    with timed_step("Spatial join: assign hex index to service requests"):
        try:
            assigned_df = assign_hex_index(sr_df, hex_gdf, error_threshold=JOIN_ERROR_THRESHOLD)
        except JoinThresholdExceededError as e:
            logger.error(f"Aborting: {e}")
            raise

    with timed_step("Validate assignments against sr_hex.csv.gz"):
        join_validation_result = validate_against_reference_df(assigned_df, sr_df)