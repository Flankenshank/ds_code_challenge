import json
import jsonschema
from jsonschema import Draft7Validator, RefResolver

def load_conformance_config(config_path):
    with open(config_path, 'r') as c_file:
        return json.load(c_file)

def get_weight(error, rule_weights, default_weight):
    """Map a jsonschema ValidationError to a weight using its property path."""
    path_parts = [str(p) for p in error.path if not isinstance(p, int)]
    key = ".".join(path_parts) if path_parts else error.validator
    return rule_weights.get(key, default_weight)

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

        total_weight = 0.0
        failed_weight = 0.0
        feature_results = []

        for i, feature in enumerate(extracted_data):
            errors = list(validator.iter_errors(feature))
            evaluated_weight = sum(rule_weights.values()) if not errors else None

            if errors:
                error_weight = sum(
                    get_weight(err, rule_weights, default_weight) for err in errors
                )
                failed_weight += error_weight
                feature_results.append({
                    "index": i,
                    "valid": False,
                    "errors": [
                        {"path": list(err.path), "message": err.message}
                        for err in errors
                    ]
                })
            else:
                feature_results.append({"index": i, "valid": True, "errors": []})

            total_weight += sum(rule_weights.values()) or default_weight

        score = 1 - (failed_weight / total_weight) if total_weight else 0.0
        label = score_to_label(score, thresholds)

        print(f"📊 Conformance score: {score:.4f} ({label})")
        print(f"   Features checked: {len(extracted_data)} | "
              f"Failed weight: {failed_weight:.2f} / {total_weight:.2f}")

        return {
            "score": score,
            "label": label,
            "total_features": len(extracted_data),
            "invalid_features": sum(1 for r in feature_results if not r["valid"]),
            "details": feature_results
        }

    except json.JSONDecodeError:
        print("❌ Error: The file is not valid JSON format.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None