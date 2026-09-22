from extract import s3client, extract_data_from_s3, load_reference_data
from validate_schema import validate_geojson
from compare_features import compare_features
from timing import timed_step

bucket = "cct-ds-code-challenge-input-data"
region = "af-south-1"
source_file = "city-hex-polygons-8-10.geojson"
comparison_file = "city-hex-polygons-8.geojson"
schema_path = "../schema.json"
config_path = "conformance_config.json"



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

    with timed_step("Reference comparison"):
        print("🔁 Commencing comparison against reference data...")
        comparison_result = compare_features(parsed_records, comparison_data)