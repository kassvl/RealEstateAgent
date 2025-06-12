"""Initialize Great Expectations project with expectation suite for listings."""
from pathlib import Path
import great_expectations as ge

GE_DIR = Path(__file__).parent.parent / "great_expectations"
GE_DIR.mkdir(exist_ok=True)

context = ge.get_context(context_root_dir=str(GE_DIR))

suite_name = "listings_basic"
try:
    suite = context.get_expectation_suite(suite_name)
except ge.exceptions.DataContextError:
    suite = context.add_expectation_suite(suite_name)

# Define expectations
cols_not_null = [
    "id",
    "price",
    "area_sqm",
    "city_name",
]
for col in cols_not_null:
    suite.add_expectation(
        {
            "expectation_type": "expect_column_values_to_not_be_null",
            "kwargs": {"column": col},
        }
    )

suite.add_expectation(
    {
        "expectation_type": "expect_column_values_to_be_between",
        "kwargs": {"column": "latitude", "min_value": -90, "max_value": 90},
    }
)
suite.add_expectation(
    {
        "expectation_type": "expect_column_values_to_be_between",
        "kwargs": {"column": "longitude", "min_value": -180, "max_value": 180},
    }
)
suite.add_expectation(
    {
        "expectation_type": "expect_column_values_to_match_regex",
        "kwargs": {"column": "currency", "regex": "^[A-Z]{3}$"},
    }
)

context.save_expectation_suite(suite)
print("Great Expectations project initialized with suite", suite_name)
