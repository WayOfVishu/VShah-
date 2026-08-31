import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const MIGRATIONS_DIR = path.join(__dirname, "migrations");

// Applies any db/migrations/*.sql file not yet recorded, in filename order.
// Each file must be idempotent (CREATE TABLE/INDEX IF NOT EXISTS) so a
// re-run is harmless even if schema_migrations somehow falls out of sync.
export function applyMigrations(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      filename   TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL DEFAULT (datetime('now'))
    )
  `);

  const applied = new Set(
    db.prepare("SELECT filename FROM schema_migrations").all().map((r) => r.filename)
  );

  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  for (const file of files) {
    if (applied.has(file)) continue;
    const sql = readFileSync(path.join(MIGRATIONS_DIR, file), "utf8");
    db.exec(sql);
    db.prepare("INSERT INTO schema_migrations (filename) VALUES (?)").run(file);
    console.log(`  applied migration: ${file}`);
  }
}
