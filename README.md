# redux-py-packages

Redux's internal Python packages — installable locally or directly from GitHub, with version pinning support. Dependencies are auto-merged from every subproject's own `requirements.txt` at install time — no manual dependency list to maintain.

## Contents

- `mt5_sdk` — MetaTrader 5 SDK/bridge utilities
- `render_requests_helper` — Render request helper utilities

## Install

**Local (editable, for development):**
```bash
pip install -e .
```

**From GitHub (latest):**
```bash
pip install git+https://github.com/<you>/redux_py_packages.git
```

**From GitHub (specific version):**
```bash
pip install git+https://github.com/<you>/redux_py_packages.git@v0.2.0
```

**Upgrade to latest:**
```bash
pip install --upgrade git+https://github.com/<you>/redux_py_packages.git
```

## Usage

```python
from redux_py_packages import mt5_sdk
from redux_py_packages.render_requests_helper import ...
```

## Adding a new subproject

1. Create `src/redux_py_packages/<new_subproject>/`
2. Give it its own `requirements.txt` if it needs dependencies
3. Commit and push — dependencies are picked up automatically, nothing else to configure

## Releasing a new version

1. Bump `version` in `pyproject.toml` and `__init__.py`
2. `git commit -am "Bump version to X.Y.Z"`
3. `git tag vX.Y.Z`
4. `git push origin main --tags`