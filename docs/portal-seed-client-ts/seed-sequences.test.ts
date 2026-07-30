import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import { describe, expect, it } from "vitest";

const HERE = __dirname; // scripts/seed-golden
const SCRIPTS_DIR = path.resolve(HERE, ".."); // scripts/
const PORTAL = path.resolve(HERE, "../.."); // portal/.build (cwd for docs + tsx)
const TSX = path.join(PORTAL, "node_modules", ".bin", "tsx");

const SCRIPTS = ["seed-acme-invoices", "seed-help-articles", "seed-kb"];

describe("portal seed-*.ts request sequences", () => {
  for (const name of SCRIPTS) {
    it(`${name} is byte-identical to its golden`, () => {
      const out = path.join(os.tmpdir(), `seedgold-${name}-${process.pid}.jsonl`);
      execFileSync(TSX, [path.join(HERE, "run-seed.mts"), path.join(SCRIPTS_DIR, `${name}.ts`)], {
        cwd: PORTAL,
        env: { ...process.env, GOLDEN_OUT: out },
        stdio: "ignore",
      });
      const actual = readFileSync(out, "utf8");
      const golden = readFileSync(path.join(HERE, "goldens", `${name}.jsonl`), "utf8");
      expect(actual).toBe(golden);
    });
  }
});
