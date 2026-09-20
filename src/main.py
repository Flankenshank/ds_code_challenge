from ds_code_challenge.src.extract import extract_data_from_s3


def main():
    geojson_data = extract_data_from_s3()
    print(geojson_data)