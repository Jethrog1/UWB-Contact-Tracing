# BRIGID Setup Notes

## Windows source setup

Install these first:

- Node.js and `npm`
- Python 3
- Conda or Miniconda

Then run:

```powershell
git clone <repo-url>
cd UWB-Contact-Tracing\BRIGID\frontend
npm install
npm run dev
```

You can also launch from:

```powershell
cd UWB-Contact-Tracing\BRIGID
.\start.ps1
```

Both flows rely on Electron startup to prepare the backend runtimes automatically.

## What startup does

When BRIGID starts from source on Windows, it provisions two runtimes:

- `BRIGID\backend\.venv`
  This is the main backend runtime. The FastAPI server and the rest of BRIGID run from here.
- `BRIGID\backend\.conda-ml-compat`
  This is the RTLS Analytics compatibility runtime. It exists only because the bundled RTLS model was trained with `scikit-learn 1.2.2`.

Important distinction:

- BRIGID actively runs the main backend from `.venv`
- BRIGID does not start a second always-running ML server
- The ML-compatible runtime is only called on demand when the RTLS `Analytics` tab runs model inference

## Manual ML runtime setup

If you ever need to prepare the analytics runtime manually:

```powershell
cd UWB-Contact-Tracing\BRIGID\backend
.\.venv\Scripts\python.exe setup_backend.py --ensure-ml-compat
```

## Failure behavior

- If BRIGID cannot create the ML compatibility runtime, startup fails clearly.
- BRIGID does not silently skip analytics support.

This is intentional, because running the bundled model under an incompatible scikit-learn version can produce broken results.