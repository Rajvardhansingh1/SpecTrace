// Copies repository data the frontend needs at build time. The Vercel project root is
// `frontend/`, so it cannot read `../samples` or `../benchmark` when it builds.
import { readFileSync, readdirSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..");

function readTree(root) {
  const out = {};
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else out[relative(root, full).split("\\").join("/")] = readFileSync(full, "utf8");
    }
  };
  walk(root);
  return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
}

const samples = {
  name: "Petstore",
  a: { label: "v1", files: readTree(join(repo, "samples", "petstore", "v1")) },
  b: { label: "v2", files: readTree(join(repo, "samples", "petstore", "v2")) },
};
writeFileSync(join(here, "..", "lib", "sample-data.json"), JSON.stringify(samples, null, 2) + "\n");

const resultsDir = join(repo, "benchmark", "v1", "results");
if (!existsSync(resultsDir)) throw new Error("No benchmark results found. Run the benchmark with --save first.");
const latest = readdirSync(resultsDir).filter((f) => f.endsWith("-all.json")).sort().at(-1);
if (!latest) throw new Error("No *-all.json benchmark result found.");
mkdirSync(join(here, "..", "data"), { recursive: true });
writeFileSync(join(here, "..", "data", "benchmark.json"), readFileSync(join(resultsDir, latest), "utf8"));
console.log(`synced samples and benchmark result ${latest}`);
