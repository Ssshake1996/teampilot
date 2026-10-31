import { mkdir, access, writeFile, symlink, readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const home = path.join(root, '.dsh-home')
const profile = path.join(home, 'profiles/teampilot')
const exists = async target => access(target).then(() => true, () => false)
await mkdir(path.join(profile, 'node_modules'), { recursive: true })
const manifest = path.join(profile, 'package.json')
if (!(await exists(manifest))) await writeFile(manifest, JSON.stringify({ name: 'teampilot-local-profile', private: true,
  dsh: { profile: { bundles: ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'] } } }, null, 2))
const patch = path.join(profile, 'cordis.patch.yml')
if (!(await exists(patch))) await writeFile(patch, `- insert:
    - id: teampilot
      name: dsh-teampilot
      config:
        baseUrl: http://127.0.0.1:8000
- id: session-telemetry-otel
  disabled: true
`)
const linked = path.join(profile, 'node_modules/dsh-teampilot')
if (!(await exists(linked))) await symlink(path.join(root, 'packages/dsh-teampilot'), linked, process.platform === 'win32' ? 'junction' : 'dir')
const runtime = JSON.parse(await readFile(path.join(root, 'node_modules/@deepseek-ai/dsh/package.json'), 'utf8'))
if (runtime.version !== '0.2.0-rc.2') throw new Error('The isolated runtime must be 0.2.0-rc.2')
const child = spawn(process.execPath, [path.join(root, 'node_modules/@deepseek-ai/dsh/lib/bin.js'), '--profile', 'teampilot',
  '--port', process.env.DSH_PORT || '5180', '--host', '127.0.0.1', '--no-open'], {
  cwd: path.dirname(root), stdio: 'inherit', env: { ...process.env, DSH_HOME: home, DSH_PERMISSION_MODE: 'workspace-write' },
})
child.on('exit', code => { process.exitCode = code ?? 1 })
process.on('SIGINT', () => child.kill('SIGINT'))
process.on('SIGTERM', () => child.kill('SIGTERM'))
