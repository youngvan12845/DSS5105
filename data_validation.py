import pandas as pd

REQUIRED_COLUMNS = ["id", "value", "category"]


def validate_dataframe(df: pd.DataFrame) -> list[str]:
    """Return validation error messages; empty list means the data passed."""
    errors = []

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"Missing columns: {missing}")

    if "value" in df.columns and df["value"].isna().any():
        errors.append("Column 'value' contains null values")

    if "id" in df.columns and df["id"].duplicated().any():
        errors.append("Column 'id' contains duplicate values")

    return errors


def main() -> None:
    sample = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [10.5, 20.0, None],
            "category": ["A", "B", "A"],
        }
    )

    errors = validate_dataframe(sample)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Validation passed.")


if __name__ == "__main__":
    main()
