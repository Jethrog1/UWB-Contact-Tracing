# BRIGID Setup Notes

## Backend runtimes

- The main BRIGID backend always runs from `BRIGID/backend/.venv`.
- The RTLS `Analytics` tab is the only feature that uses a second Python runtime:
  `BRIGID/backend/.conda-ml-compat`.
- That second runtime exists because the bundled RTLS model was trained with
  `scikit-learn 1.2.2` and must be inferred under a matching stack.

## First-time setup

1. Install Conda or Miniconda on the machine.
2. Start BRIGID normally.

BRIGID now provisions both runtimes during startup:

- `backend/.venv` for the normal FastAPI backend and the rest of the app
- `backend/.conda-ml-compat` for RTLS analytics model inference only

If you want to prepare the analytics runtime manually, run:

```bash
cd BRIGID/backend
.venv/bin/python setup_backend.py --ensure-ml-compat
```

## Important behavior

- If the compatibility runtime cannot be created, BRIGID setup now fails loudly
  instead of silently skipping analytics support.
- This keeps the app setup reproducible on another machine and avoids running
  the bundled model under an incompatible scikit-learn version.
