const { spawn } = require('child_process')
const path = require('path')

const args = process.argv.slice(2)
const env = { ...process.env }

delete env.ELECTRON_RUN_AS_NODE

const projectRoot = path.resolve(__dirname, '..')
const cliEntrypoint = path.join(projectRoot, 'node_modules', 'electron-vite', 'bin', 'electron-vite.js')

const child = spawn(process.execPath, [cliEntrypoint, ...args], {
  cwd: projectRoot,
  env,
  stdio: 'inherit',
})

child.on('exit', (code) => {
  process.exit(code ?? 0)
})

child.on('error', (error) => {
  console.error(error)
  process.exit(1)
})
