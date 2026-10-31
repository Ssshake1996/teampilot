import { build } from 'esbuild'
import { cp, mkdir, writeFile, readFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
process.chdir(root)
const tsc = path.resolve(root, '../../node_modules/typescript/bin/tsc')
execFileSync(process.execPath, [tsc, '-b', 'tsconfig.host.json'], { stdio: 'inherit' })
const workspace = path.resolve(root, '../..')
// The published generator identifies protocol symbols only through workspace
// registrations. Stage the exact installed declarations; never patch upstream.
const reflection = path.join(workspace, 'packages/.protocol-reflection')
await mkdir(reflection, { recursive: true })
await cp(path.join(workspace, 'node_modules/@deepseek-ai/dsh-typert-protocol/lib/types'), reflection, { recursive: true })
await writeFile(path.join(reflection, 'package.json'), JSON.stringify({name:'@deepseek-ai/dsh-typert-protocol',exports:{'.':{types:'./index.d.ts'}}}))
await writeFile(path.join(reflection, 'tsconfig.json'), JSON.stringify({compilerOptions:{skipLibCheck:true},include:['**/*.d.ts']}))
const aggregate = JSON.parse(await readFile(path.join(workspace, 'tsconfig.host.json'), 'utf8'))
const generationConfig = {...aggregate, compilerOptions:{...aggregate.compilerOptions,paths:{'@deepseek-ai/dsh-typert-protocol':['./packages/.protocol-reflection/index.d.ts']}},references:[...aggregate.references,{path:'./packages/.protocol-reflection/tsconfig.json'}]}
await writeFile(path.join(workspace, 'tsconfig.reflection.json'), JSON.stringify(generationConfig))
// Generator exposes only the conventional aggregate filename. Use its analyzer
// directly with a dedicated generated config, keeping checked-in config intact.
const { WorkspaceAnalyzer, FaceModelEmitter } = await import('@deepseek-ai/dsh-typert-generator')
const model = new WorkspaceAnalyzer({root:workspace,hostConfig:'tsconfig.reflection.json',faces:['host'],packages:['dsh-teampilot']}).analyze()
const results = model.faces.flatMap(face => {
  const emitter = new FaceModelEmitter(face)
  return face.packages.filter(p => p.name === 'dsh-teampilot').map(p => emitter.emit(p.name))
})
if (results.length !== 1 || !results[0].remote) throw new Error('Missing generated Remote contribution')
const result = results[0]
await mkdir('lib', { recursive: true })
await writeFile('lib/typert.host.js', result.js)
await writeFile('lib/typert.host.d.ts', result.dts)
await writeFile('lib/typert.remote-client.js', result.remote.js)
await writeFile('lib/typert.remote-client.d.ts', result.remote.dts)
await build({ entryPoints: ['src/host/index.ts'], outfile: 'lib/index.js', bundle: true, platform: 'node', target: 'node22', format: 'esm', packages: 'external' })
await build({ entryPoints: ['src/host/preset.ts'], outfile: 'lib/preset.js', bundle: true, platform: 'node', target: 'node22', format: 'esm', packages: 'external' })
execFileSync(process.execPath, [tsc, '-p', 'tsconfig.client.json'], { stdio: 'inherit' })
await build({ entryPoints: ['src/client/index.tsx'], outfile: 'lib/client.js', bundle: true, platform: 'browser', format: 'cjs',
  jsx: 'automatic', tsconfig: 'tsconfig.client.json', target: 'es2022',
  external: ['react', 'react/jsx-runtime', '@deepseek-ai/cordis', '@deepseek-ai/dsh-client-ui-primitives'],
  loader: { '.css': 'text' },
  banner: { js: 'window.__ModuleLoader__.load({id:"dsh-teampilot",factory:function(require){var module={exports:{}};var exports=module.exports;' }, footer: { js: 'return module.exports;}});' },
})
