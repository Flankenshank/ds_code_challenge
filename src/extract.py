import json
import boto3

from aws_client import fetch_client_keys

bucket="cct-ds-code-challenge-input-data"
region="af-south-1"
source_file="city-hex-polygons-8-10.geojson"
comparison_file="city-hex-polygons-8.geojson"

def s3client():
    return boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=fetch_client_keys()[ "s3" ][ "access_key" ],
        aws_secret_access_key=fetch_client_keys()[ "s3" ][ "secret_key" ]
    )

def load_reference_data(client, bucket, key):
    response = client.get_object(Bucket=bucket, Key=key)
    bytes_data = response['Body'].read()
    feature_collection = json.loads(bytes_data)
    return feature_collection['features']

def extract_data_from_s3(client, bucket, source_file, resolution=8):
    response = client.select_object_content(
        Bucket=bucket,
        Key=source_file,
        Expression="SELECT * FROM S3Object[*].features[*] f WHERE f.properties.resolution = " + str(int(resolution)),
        ExpressionType="SQL",
        InputSerialization={"JSON": {"Type": "DOCUMENT"}},
        OutputSerialization={"JSON": {}}
    )
    parsed_records = parse_records(response['Payload'])
    return parsed_records

def parse_records(events):
    features = []
    buffer = b""
    for event in events:
        if "Records" in event:
            buffer += event["Records"]["Payload"]
            pieces = buffer.split(b"\n")
            for p in pieces[:-1]:
                if p:
                    features.append(json.loads(p.decode("utf-8")))
            buffer = pieces[-1]
    if buffer.strip():
        features.append(json.loads(buffer.decode("utf-8")))
    return features

if __name__ == "__main__":
    client = s3client()
    parsed_records = extract_data_from_s3(client, bucket, source_file)
    comparison_data = load_reference_data(client, bucket, comparison_file)
    print(len(parsed_records), len(comparison_data))
