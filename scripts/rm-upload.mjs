#!/usr/bin/env node
/**
 * Upload a PDF to reMarkable Cloud (rmapi-js v9).
 *
 * Env vars:
 *   TOKEN_FILE          — path to the device token file
 *   DOC_NAME            — visible name on the tablet
 *   PDF_PATH            — local path to the PDF file
 *   FOLDER_NAME         — reMarkable folder path, e.g. "Articles/Inbox"
 *                         use "" or omit to upload to root
 *   REMARKABLE_FOLDER_ID — UUID of the target folder (skips the name lookup
 *                          entirely — much faster on large libraries). Takes
 *                          precedence over FOLDER_NAME.
 *
 * Writes JSON to stdout: {"id":"...","hash":"...","name":"...","parentId":"..."}
 * Writes progress to stderr.
 */
import { remarkable } from "rmapi-js";
import { readFileSync } from "node:fs";

const { TOKEN_FILE, DOC_NAME, PDF_PATH, FOLDER_NAME, REMARKABLE_FOLDER_ID } = process.env;

if (!TOKEN_FILE || !DOC_NAME || !PDF_PATH) {
  console.error("rm-upload: TOKEN_FILE, DOC_NAME, and PDF_PATH are required");
  process.exit(1);
}

const token = readFileSync(TOKEN_FILE, "utf-8").trim();
const pdfBytes = readFileSync(PDF_PATH);

// v9: remarkable() is async
const api = await remarkable(token);

// ── Resolve target folder id ──────────────────────────────────────────────
let parentId = ""; // "" = root

if (REMARKABLE_FOLDER_ID) {
  // Fast path: caller already knows the UUID, skip listing entirely
  parentId = REMARKABLE_FOLDER_ID;
  console.error(`  Using folder id directly: ${parentId}`);

} else if (FOLDER_NAME) {
  // Slow path: look up folder by name using batched metadata fetches.
  // listIds() is cheap (one request). getMetadata() per-item is expensive
  // so we do it in batches of 10 to avoid saturating the connection.
  const parts = FOLDER_NAME.replace(/^\//, "").split("/").filter(Boolean);
  console.error(`  Resolving folder path: ${FOLDER_NAME}`);

  const ids = await api.listIds();
  console.error(`  Got ${ids.length} item ids. Scanning for folders...`);

  const items = await fetchMetadataBatched(api, ids, 10);

  let currentParentId = "";
  let resolved = true;
  for (const part of parts) {
    const match = items.find(
      (i) => i.type === "CollectionType"
          && i.visibleName === part
          && i.parent === currentParentId
    );
    if (!match) {
      console.error(`  Warning: folder "${part}" not found (path: ${FOLDER_NAME}). Uploading to root.`);
      resolved = false;
      break;
    }
    currentParentId = match.id;
  }

  if (resolved) {
    parentId = currentParentId;
    console.error(`  Folder resolved: ${FOLDER_NAME} → id ${parentId}`);
    console.error(`  Tip: set REMARKABLE_FOLDER_ID=${parentId} in .env to skip this scan next time.`);
  }
}

// ── Upload PDF directly into the target folder ─────────────────────────────
const entry = await api.putPdf(DOC_NAME, pdfBytes, { parent: parentId });
const dest = parentId ? `folder id ${parentId}` : "root";
console.error(`  Uploaded "${DOC_NAME}" → ${dest}`);

console.log(JSON.stringify({ id: entry.id, hash: entry.hash, name: DOC_NAME, parentId }));

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Fetch metadata for all items in small parallel batches.
 * Returns array of { id, hash, type, visibleName, parent, ... }.
 * Failures on individual items are silently skipped.
 */
async function fetchMetadataBatched(api, ids, concurrency) {
  const results = [];
  for (let i = 0; i < ids.length; i += concurrency) {
    const batch = ids.slice(i, i + concurrency);
    const metas = await Promise.all(
      batch.map(async ({ id, hash }) => {
        try {
          const meta = await api.getMetadata(hash);
          return { id, hash, ...meta };
        } catch {
          return null; // skip timed-out or missing entries
        }
      })
    );
    results.push(...metas.filter(Boolean));

    // Early exit: stop scanning once we've seen enough CollectionType items
    // to resolve the full path. Saves time on large libraries.
    const folders = results.filter((r) => r.type === "CollectionType");
    if (_pathResolvable(folders, (FOLDER_NAME || "").replace(/^\//, "").split("/").filter(Boolean))) {
      console.error(`  Found all needed folders after scanning ${i + batch.length}/${ids.length} items.`);
      break;
    }
  }
  return results;
}

/**
 * Returns true if the given folder list already contains enough entries
 * to resolve every component of the target path.
 */
function _pathResolvable(folders, parts) {
  let currentParentId = "";
  for (const part of parts) {
    const match = folders.find(
      (f) => f.visibleName === part && f.parent === currentParentId
    );
    if (!match) return false;
    currentParentId = match.id;
  }
  return true;
}
