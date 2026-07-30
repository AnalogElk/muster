/**
 * Run a seed script under the fetch-stub harness and emit its recorded request
 * sequence as JSONL. Usage:
 *   GOLDEN_OUT=goldens/<name>.jsonl tsx run-seed.mts <abs path to seed-*.ts>
 * Emits to GOLDEN_OUT if set, else stdout.
 */
import { writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

import { dumpJsonl, freezeTime, installFetch } from "./harness.mts";

// Fixed fake env so goldens carry a dummy bearer, never a real secret.
process.env.ELK_CMS_TOKEN = "SEED_TEST_TOKEN";
process.env.DIRECTUS_TOKEN = "SEED_TEST_TOKEN";
process.env.DIRECTUS_URL = "https://cms.analogelk.com";
delete process.env.NEXT_PUBLIC_DIRECTUS_URL;

freezeTime();
installFetch();

const out = process.env.GOLDEN_OUT;
process.on("exit", () => {
  const text = dumpJsonl();
  if (out) writeFileSync(out, text);
  else process.stdout.write(text);
});

const target = process.argv[2];
// Scripts guarded by `argv[1].endsWith("<name>.ts")` need argv[1] to be the target.
process.argv[1] = target;
await import(pathToFileURL(target).href);
