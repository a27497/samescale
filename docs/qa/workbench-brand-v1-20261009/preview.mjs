import { fileURLToPath, pathToFileURL } from 'node:url'
import { resolve } from 'node:path'
const root = fileURLToPath(new URL('../../../frontend/', import.meta.url))
const { preview } = await import(pathToFileURL(resolve(root, 'node_modules/vite/dist/node/index.js')).href)
const artifacts = resolve(process.argv[2] ?? '/tmp/samescale-workbench-brand-v1')
const guard = {
  name: 'brand-qa-read-only-guard',
  configurePreviewServer(server) {
    server.middlewares.use((req, res, next) => {
      const path = new URL(req.url, 'http://localhost').pathname
      const allowed = ['GET', 'HEAD'].includes(req.method) || (req.method === 'POST' && path === '/api/workbench/regression/compare')
      if (path.startsWith('/api/') && !allowed) { res.statusCode = 403; res.end('Brand QA permits only reads and saved-evidence comparison'); return }
      next()
    })
  },
}
for (const [name, port] of [['baseline', 5190], ['brand', 5191]]) {
  const server = await preview({ root, configFile: false, plugins: [guard], build: { outDir: resolve(artifacts, name + '-dist') }, preview: { host: '127.0.0.1', port, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8000' } } })
  server.printUrls()
}
