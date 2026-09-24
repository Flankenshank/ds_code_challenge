# data_transformation.py
"""
Join service request data to H3 resolution-8 hexagons.

Input columns expected on the service request dataset:
    notification_number, latitude, longitude  (plus other descriptive columns)

If the source already carries an `h3_level8_index` column (e.g. because the
same file doubles as the validation reference), it is dropped before the
join so the freshly computed index doesn't collide with, or get confused
with, the existing one.
"""
import io
import geopandas as gpd
import pandas as pd
from timing import logger


def load_hex_polygons_from_s3(client, bucket, key):
    """Load the resolution-8 hex polygons as a GeoDataFrame keyed by H3 index."""
    response = client.get_object(Bucket=bucket, Key=key)
    bytes_data = response['Body'].read()
    gdf = gpd.read_file(io.BytesIO(bytes_data))
    gdf = gdf[["index", "geometry"]].rename(columns={"index": "h3_level8_index"})
    return gdf


def load_service_requests(path_or_url, sep=","):
    """Load the service request dataset from a local path or URL."""
    return pd.read_csv(path_or_url, compression="gzip", sep=sep)


def read_url_from_file(url_file_path):
    """
    Read the target URL out of a .url file.
    Handles both a plain-text file containing just the URL, and a Windows
    .url shortcut file (INI-style, with a `URL=` line under [InternetShortcut]).
    """
    with open(url_file_path) as f:
        content = f.read().strip()

    for line in content.splitlines():
        if line.startswith("URL="):
            return line[len("URL="):].strip()

    # Fallback: assume the whole file content is just the URL
    return content


class JoinThresholdExceededError(Exception):
    """Raised when the proportion of service requests failing to join to a
    hexagon exceeds the configured error threshold."""
    pass


def assign_hex_index(sr_df, hex_gdf, error_threshold=0.01):
    """
    Spatially join each service request to the H3 resolution-8 hexagon
    containing its latitude/longitude.

    - Requests with missing latitude/longitude get h3_level8_index = 0
      (per spec) and are NOT counted as join failures, since they were
      never expected to join.
    - Requests WITH coordinates that fail to match any hexagon ARE counted
      as join failures, since that indicates bad data (out-of-bounds
      coordinates, swapped lat/lon, precision issues, etc).
    - If failed joins exceed error_threshold (as a fraction of requests
      that had coordinates), raise JoinThresholdExceededError rather than
      silently continuing.
    """
    sr_df = sr_df.drop(columns=["h3_level8_index"], errors="ignore")

    has_coords = sr_df["latitude"].notna() & sr_df["longitude"].notna()
    valid = sr_df[has_coords].copy()
    missing = sr_df[~has_coords].copy()
    missing["h3_level8_index"] = 0

    points = gpd.GeoDataFrame(
        valid,
        geometry=gpd.points_from_xy(valid["longitude"], valid["latitude"]),
        crs="EPSG:4326",
    )

    joined = gpd.sjoin(points, hex_gdf, how="left", predicate="within")

    # A point could match >1 polygon if it falls exactly on a shared edge/vertex.
    dup_count = joined.index.duplicated().sum()
    if dup_count:
        logger.warning(f"{dup_count} requests matched more than one hexagon (boundary points); keeping first match")
    joined = joined[~joined.index.duplicated(keep="first")]

    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")

    # Points with coordinates that matched no hexagon at all
    unmatched_mask = joined["h3_level8_index"].isna()
    unmatched_count = int(unmatched_mask.sum())
    attempted = len(valid)
    failure_rate = (unmatched_count / attempted) if attempted else 0.0

    logger.info(
        f"Join summary: {attempted} requests with coordinates, "
        f"{unmatched_count} failed to join ({failure_rate:.4%}), "
        f"{len(missing)} had missing coordinates (assigned index 0)"
    )

    if failure_rate > error_threshold:
        raise JoinThresholdExceededError(
            f"Join failure rate {failure_rate:.4%} exceeds threshold "
            f"{error_threshold:.4%} ({unmatched_count}/{attempted} requests unmatched)"
        )

    result = pd.concat([joined, missing], ignore_index=True)
    return result


def validate_against_reference(assigned_df, reference_path_or_url, id_column="notification_number", sep=","):
    reference_df = pd.read_csv(reference_path_or_url, compression="gzip", sep=sep)

    merged = assigned_df.merge(
        reference_df[[id_column, "h3_level8_index"]],
        on=id_column,
        suffixes=("_computed", "_reference"),
    )

    has_coords_mask = merged["h3_level8_index_computed"] != 0
    coord_rows = merged[has_coords_mask]
    no_coord_rows = merged[~has_coords_mask]

    coord_mismatches = coord_rows[
        coord_rows["h3_level8_index_computed"] != coord_rows["h3_level8_index_reference"]
    ]
    coord_match_rate = 1 - (len(coord_mismatches) / len(coord_rows)) if len(coord_rows) else 0.0

    logger.info(
        f"Hex assignment match rate (rows with coordinates only): "
        f"{coord_match_rate:.4%} ({len(coord_mismatches)} mismatches / {len(coord_rows)} compared)"
    )
    logger.info(
        f"Rows with missing coordinates: {len(no_coord_rows)} (set to 0 per spec; "
        f"reference file's representation for these rows may differ)"
    )

    return {
        "match_rate": coord_match_rate,
        "total_compared": len(coord_rows),
        "mismatches": coord_mismatches,
        "missing_coord_rows": len(no_coord_rows),
    }