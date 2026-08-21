import pandas as pd

from data_validation import validate_dataframe


def main() -> None:
    sample = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "value": [10.5, 20.0, 30.0],
            "category": ["A", "B", "A"],
        }
    )

    print("Hello from dss5105!")
    print(f"pandas {pd.__version__}")

    errors = validate_dataframe(sample)
    if errors:
        print("Sample data failed validation.")
    else:
        print("Sample data passed validation.")


if __name__ == "__main__":
    main()
