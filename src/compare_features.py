def normalize_ring(ring, decimals=7):
    """Round coordinates and drop the duplicated closing point for comparison."""
    rounded = [[round(lon, decimals), round(lat, decimals)] for lon, lat in ring]
    if rounded and rounded[0] == rounded[-1]:
        rounded = rounded[:-1]
    return rounded


def rings_match(ring_a, ring_b, decimals=7):
    """
    Compare two polygon rings allowing for different starting vertex
    and winding direction, since these don't change the actual shape.
    """
    norm_a = normalize_ring(ring_a, decimals)
    norm_b = normalize_ring(ring_b, decimals)

    if len(norm_a) != len(norm_b):
        return False

    # Try every rotation of ring_b, forward and reversed, against ring_a
    candidates = [norm_b, norm_b[::-1]]
    n = len(norm_b)
    for candidate in candidates:
        for offset in range(n):
            rotated = candidate[offset:] + candidate[:offset]
            if rotated == norm_a:
                return True
    return False


def polygons_match(geom_a, geom_b, decimals=7):
    """
    Compare two GeoJSON Polygon geometries with coordinate rounding,
    ignoring closing-point duplication, winding direction, and start vertex.
    """
    if geom_a.get("type") != geom_b.get("type"):
        return False
    if geom_a.get("type") != "Polygon":
        return geom_a == geom_b  # fallback for non-polygon types

    rings_a = geom_a.get("coordinates", [])
    rings_b = geom_b.get("coordinates", [])

    if len(rings_a) != len(rings_b):
        return False

    return all(
        rings_match(ra, rb, decimals) for ra, rb in zip(rings_a, rings_b)
    )

def compare_features(extracted_data, reference_data, coord_tolerance=1e-9):
    """
    Compare extracted features against a reference/verification dataset,
    matched by H3 index.
    """
    extracted_by_index = {f["properties"]["index"]: f for f in extracted_data}
    reference_by_index = {f["properties"]["index"]: f for f in reference_data}

    extracted_indices = set(extracted_by_index.keys())
    reference_indices = set(reference_by_index.keys())

    missing_from_extracted = reference_indices - extracted_indices
    extra_in_extracted = extracted_indices - reference_indices
    common_indices = extracted_indices & reference_indices

    mismatches = []
    for idx in common_indices:
        ext_props = extracted_by_index[idx]["properties"]
        ref_props = reference_by_index[idx]["properties"]

        diffs = {}
        for field in ("centroid_lat", "centroid_lon"):
            ext_val = ext_props.get(field)
            ref_val = ref_props.get(field)
            if ext_val is None or ref_val is None or abs(ext_val - ref_val) > coord_tolerance:
                diffs[field] = {"extracted": ext_val, "reference": ref_val}

        ext_geom = extracted_by_index[idx].get("geometry")
        ref_geom = reference_by_index[idx].get("geometry")
        if not polygons_match(ext_geom, ref_geom, decimals=7):
            diffs["geometry"] = "mismatch"

        if diffs:
            mismatches.append({"index": idx, "diffs": diffs})

    total_reference = len(reference_indices)
    exact_matches = len(common_indices) - len(mismatches)
    match_rate = exact_matches / total_reference if total_reference else 0.0

    result = {
        "match_rate": match_rate,
        "total_reference": total_reference,
        "total_extracted": len(extracted_indices),
        "exact_matches": exact_matches,
        "missing_from_extracted": sorted(missing_from_extracted),
        "extra_in_extracted": sorted(extra_in_extracted),
        "mismatches": mismatches,
    }

    print(f"🔁 Comparison match rate: {match_rate:.4%}")
    print(f"   Reference: {total_reference} | Extracted: {len(extracted_indices)} | "
          f"Exact matches: {exact_matches}")
    if missing_from_extracted:
        print(f"   ⚠️  {len(missing_from_extracted)} indices in reference but missing from extracted")
    if extra_in_extracted:
        print(f"   ⚠️  {len(extra_in_extracted)} indices in extracted but not in reference")
    if mismatches:
        print(f"   ⚠️  {len(mismatches)} common indices have field-level differences")

    return result