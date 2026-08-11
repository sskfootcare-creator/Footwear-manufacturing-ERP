# Online Commerce Test Report

## Tests added
- `backend/tests/test_online_commerce_guards.py::test_deduct_from_specific_location_requires_reserved_stock`
- `backend/tests/test_online_commerce_guards.py::test_normalized_marketplace_keys_collapse_case_space_hyphen_exactly`

## Tests passed
- `python3 -m py_compile backend/server.py`
- `pytest -q -c /dev/null backend/tests/test_online_commerce_guards.py`

## Tests failed / warnings
- `pytest -q backend/tests/test_online_commerce_guards.py` and `cd backend && pytest -q tests/test_online_commerce_guards.py` failed because `pytest-xdist` is required by `backend/pytest.ini` but is not installed in the active Python environment.
- `python3 -m pip install pytest-xdist` failed because package index access returned 403 Forbidden from the environment.

## Not verified
- Full test suite, B2B, production, inventory, WMS, reconciliation, and profitability regression suites were not fully run because the configured required pytest plugin is unavailable in this environment.
- Settlement idempotency was audited but not fixed without real platform row identity confirmation.
- B2B-vs-online allocation policy remains BUSINESS RULE NOT IMPLEMENTED / NOT VERIFIED.
