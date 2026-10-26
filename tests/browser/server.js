/* Static assets for browser behaviour tests. API responses are explicit offline fixtures. */
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {dirname, resolve, join, extname} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

export async function assets(relativeFolder) {
  const folder = resolve(root, relativeFolder);
  if (!folder.startsWith(root + '/')) throw new Error('asset root must stay in the repository');
  const server = createServer(async (request, response) => {
    const path = new URL(request.url, 'http://127.0.0.1').pathname;
    if (!/^\/(?:index\.html|[a-z]+\.(?:js|css)|typeface\/[a-z0-9-]+\.woff2)?$/.test(path)) {
      response.writeHead(404); response.end(); return;
    }
    try {
      const file = path === '/' ? 'index.html' : path.slice(1);
      const types = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2'};
      response.setHeader('Content-Type', types[extname(file)]);
      response.end(await readFile(join(folder, file)));
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {origin: 'http://127.0.0.1:' + server.address().port,
    close: () => new Promise(resolve => server.close(resolve))};
}
