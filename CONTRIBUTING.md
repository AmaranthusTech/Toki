# Contributing to Toki

Thanks for your interest in contributing!

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Running the API

```bash
uvicorn jcal.api.app:app --reload --app-dir src
```

## Tests

```bash
pytest -q
```

If you don't have the reference data or ephemeris files, some tests will be skipped.

## Pull Requests
- Keep PRs focused and small.
- Add or update tests for behavior changes.
- Update documentation when you change public APIs.

## Code Style
- Keep existing formatting and naming conventions.
- Avoid introducing new dependencies unless necessary.
