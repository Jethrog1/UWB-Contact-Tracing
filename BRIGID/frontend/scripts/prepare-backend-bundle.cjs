const { existsSync } = require('fs')
const { execFileSync } = require('child_process')
const path = require('path')

const frontendRoot = path.resolve(__dirname, '..')
const brigidRoot = path.resolve(frontendRoot, '..')
const backendRoot = path.join(brigidRoot, 'backend')
const assetsRoot = path.join(brigidRoot, 'assets')

const backendPython = process.platform === 'win32'
  ? path.join(backendRoot, '.venv', 'Scripts', 'python.exe')
  : path.join(backendRoot, '.venv', 'bin', 'python')

const compatPython = process.platform === 'win32'
  ? path.join(backendRoot, '.conda-ml-compat', 'Scripts', 'python.exe')
  : path.join(backendRoot, '.conda-ml-compat', 'bin', 'python')

const modelBundle = path.join(assetsRoot, 'ML', 'final_model_bundle.pkl')

function fail(message) {
  console.error(`[prepare-backend-bundle] ${message}`)
  process.exit(1)
}

function run(command, args, cwd) {
  execFileSync(command, args, {
    cwd,
    stdio: 'inherit',
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })
}

if (!existsSync(backendPython)) {
  fail('Missing backend/.venv runtime. Start BRIGID once or create the backend venv before packaging.')
}

if (!existsSync(modelBundle)) {
  fail('Missing assets/ML/final_model_bundle.pkl. The packaged build must include the bundled RTLS analytics model.')
}

run(backendPython, ['setup_backend.py', '--ensure-ml-compat'], backendRoot)

if (!existsSync(compatPython)) {
  fail('Missing backend/.conda-ml-compat runtime after setup. Packaging cannot continue.')
}

console.log('[prepare-backend-bundle] Backend runtimes and ML assets are ready for packaging.')
