import { NodeGlobalsPolyfillPlugin } from "@esbuild-plugins/node-globals-polyfill";
import { build } from "esbuild";
import { mkdir, copyFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outdir = path.join(root, "src", "boltz_web", "static", "vendor", "ketcher");
const entry = path.join(root, "frontend", "ketcher-entry.jsx");

await mkdir(outdir, { recursive: true });

await build({
  entryPoints: [entry],
  bundle: true,
  minify: true,
  sourcemap: false,
  format: "iife",
  target: ["es2020"],
  outfile: path.join(outdir, "boltz-ketcher.js"),
  loader: {
    ".svg": "dataurl",
    ".png": "dataurl",
    ".jpg": "dataurl",
    ".gif": "dataurl",
    ".woff": "dataurl",
    ".woff2": "dataurl",
    ".ttf": "dataurl",
  },
  define: {
    "process.env.NODE_ENV": '"production"',
    global: "globalThis",
  },
  plugins: [
    NodeGlobalsPolyfillPlugin({
      process: true,
      buffer: true,
    }),
  ],
});

async function copyRuntimeAssets(sourceDir) {
  const entries = await readdir(sourceDir);
  await Promise.all(
    entries.map(async (entryName) => {
      const source = path.join(sourceDir, entryName);
      const info = await stat(source);
      if (info.isDirectory()) return;
      if (!/\.(wasm|worker\.js|data)$/i.test(entryName)) return;
      await copyFile(source, path.join(outdir, entryName));
    }),
  );
}

await copyRuntimeAssets(path.join(root, "node_modules", "ketcher-standalone", "dist"));
await copyRuntimeAssets(path.join(root, "node_modules", "ketcher-standalone", "dist", "binaryWasm"));

console.log(`Ketcher assets written to ${outdir}`);
