import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = process.cwd();
const htmlPath = resolve(root, 'dist/index.html');
let html = await readFile(htmlPath, 'utf8');

const assetsDir = resolve(root, 'dist/assets');
const cssMatch = html.match(/<link[^>]+rel="stylesheet"[^>]+href="(?:\.\/)?\/?assets\/([^"]+)"[^>]*>/);
if (cssMatch) {
  const css = await readFile(resolve(assetsDir, cssMatch[1]), 'utf8');
  html = html.replace(cssMatch[0], `<style>\n${css}\n</style>`);
}

const jsMatch = html.match(/<script[^>]+src="(?:\.\/)?\/?assets\/([^\"]+)"[^>]*><\/script>/);
if (!jsMatch) throw new Error('standalone build: app script not found');
const js = (await readFile(resolve(assetsDir, jsMatch[1]), 'utf8')).replace(/<\/script/gi, '<\\/script');
html = html.replace(jsMatch[0], `<script type="module">\n${js}\n</script>`);

const out = resolve(root, '洛阳盛唐浮空古塔.html');
await writeFile(out, html, 'utf8');
console.log(out);
