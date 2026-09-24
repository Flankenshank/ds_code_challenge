import json
from jsonschema import Draft7Validator, RefResolver
from timing import logger


def load_conformance_config(config_path):
    with open(config_path, 'r') as c_file:
        return json.load(c_file)


def rule_keys_for_error(error):
    """
    Map a jsonschema ValidationError to the rule key(s) used in rule_weights.

    - A missing required property is reported at the parent object, so the
      property name is added to the path (e.g. properties.index).
    - A top-level `type` error is mapped to `feature.type`.
    - Integer path parts (array positions) are dropped so that any error
      inside geometry.coordinates maps to the same rule.
    """
    path_parts = [str(p) for p in error.path if not isinstance(p, int)]

    if error.validator == "required":
        missing = [p for p in error.validator_value if p not in error.instance]
        return [".".join(path_parts + [name]) for name in missing]

    key = ".".join(path_parts) if path_parts else str(error.validator)
    if key == "type":
        key = "feature.type"
    return [key]


def score_to_label(score, thresholds):
    for tier in thresholds:
        if score >= tier["min_score"]:
            return tier["label"]
    return thresholds[-1]["label"]


def validate_geojson(extracted_data, schema_path, config_path):
    try:
        with open(schema_path, 'r') as s_file:
            validation_schema = json.load(s_file)

        config = load_conformance_config(config_path)
        rule_weights = config["rule_weights"]
        default_weight = config["default_weight"]
        thresholds = sorted(config["thresholds"], key=lambda t: -t["min_score"])

        # Validate each feature individually against the feature definition
        feature_def = validation_schema["definitions"]["feature"]
        resolver = RefResolver.from_schema(validation_schema)
        validator = Draft7Validator(feature_def, resolver=resolver)

        weight_per_feature = sum(rule_weights.values())
        total_weight = 0.0
        failed_weight = 0.0
        feature_results = []

        for position, feature in enumerate(extracted_data):
            errors = list(validator.iter_errors(feature))

            # Each rule is charged at most once per feature, however many
            # errors it produced (e.g. many bad points in one polygon).
            failed_rules = {key for err in errors for key in rule_keys_for_error(err)}
            feature_failed_weight = sum(
                rule_weights.get(key, default_weight) for key in failed_rules
            )

            failed_weight += feature_failed_weight
            total_weight += weight_per_feature

            feature_results.append({
                "position": position,
                "h3_index": (feature.get("properties") or {}).get("index"),
                "valid": not errors,
                "failed_rules": sorted(failed_rules),
                "errors": [
                    {"path": list(err.path), "message": err.message}
                    for err in errors
                ],
            })

        score = 1 - (failed_weight / total_weight) if total_weight else 0.0
        label = score_to_label(score, thresholds)

        logger.info(f"Conformance score: {score:.4f} ({label})")
        logger.info(
            f"Features checked: {len(extracted_data)} | "
            f"Failed weight: {failed_weight:.2f} / {total_weight:.2f}"
        )

        return {
            "score": score,
            "label": label,
            "total_features": len(extracted_data),
            "invalid_features": sum(1 for r in feature_results if not r["valid"]),
            "details": feature_results,
        }

    except json.JSONDecodeError:
        logger.exception("The schema or config file is not valid JSON")
        raise
    except Exception:
        logger.exception("Unexpected error during conformance validation")
        raise