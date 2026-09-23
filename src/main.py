from extract import s3client, extract_data_from_s3, load_reference_data
from validate_schema import validate_geojson
from compare_features import compare_features
from timing import timed_step, logger
from data_transformation import (
    load_hex_polygons_from_s3, load_service_requests, assign_hex_index,
    validate_against_reference, JoinThresholdExceededError, read_url_from_file
)



bucket = "cct-ds-code-challenge-input-data"
region = "af-south-1"
source_file = "city-hex-polygons-8-10.geojson"
comparison_file = "city-hex-polygons-8.geojson"
schema_path = "../schema.json"
config_path = "conformance_config.json"
new_data = "city-hex-polygons-8.geojson"



if __name__ == "__main__":
    client = s3client()

    with timed_step("S3 extraction"):
        print("📥 Extracting data streams from S3...")
        parsed_records = extract_data_from_s3(client, bucket, source_file)
        comparison_data = load_reference_data(client, bucket, comparison_file)
        print(f"📦 Records downloaded -> Extracted: {len(parsed_records)}, Reference: {len(comparison_data)}")

    with timed_step("Schema validation"):
        print("🔎 Commencing local schema validation process...")
        result = validate_geojson(parsed_records, schema_path, config_path)

    if result is not None:
        if result["invalid_features"] > 0:
            print(f"⚠️  {result['invalid_features']} of {result['total_features']} features failed one or more checks.")
        else:
            print("✅ All features passed schema validation.")

    with timed_step("Load hex polygons and service requests"):
        hex_gdf = load_hex_polygons_from_s3(client, bucket, "city-hex-polygons-8.geojson")
        sr_url = read_url_from_file("../data/sr_hex.csv.gz.url")
        sr_df = load_service_requests(sr_url)

    with timed_step("Spatial join: assign hex index to service requests"):
        try:
            assigned_df = assign_hex_index(sr_df, hex_gdf, error_threshold=0.01)
        except JoinThresholdExceededError as e:
            logger.error(f"Aborting: {e}")
            raise

    with timed_step("Validate assignments against sr_hex.csv.gz"):
        join_validation_result = validate_against_reference(assigned_df, sr_url)