#!/usr/bin/env node
/**
 * Upload a PDF or ePub to reMarkable Cloud (rmapi-js v9).
 *
 * Env vars:
 *   TOKEN_FILE          — path to the device token file
 *   DOC_NAME            — visible name on the tablet
 *   FILE_PATH           — local path to the file
 *   FILE_TYPE           — "epub" (default) or "pdf"
 *   FOLDER_NAME         — reMarkable folder path, e.g. "Articles/Inbox"
 *   REMARKABLE_FOLDER_ID — UUID of the target folder (skips name lookup)
 *
 * Writes JSON to stdout: {"id":"...","hash":"...","name":"...","parentId":"..."}
 * Writes progress to stderr.
 */
import { remarkable } from "rmapi-js";
import { readFileSync } from "node:fs";

const { TOKEN_FILE, DOC_NAME, FILE_PATH, FILE_TYPE = "epub", FOLDER_NAME, REMARKABLE_FOLDER_ID } = process.env;

if (!TOKEN_FILE || !DOC_NAME || !FILE_PATH) {
  console.error("rm-upload: TOKEN_FILE, DOC_NAME, and FILE_PATH are required");
  process.exit(1);
}

const token = readFileSync(TOKEN_FILE, "utf-8").trim();
const fileBytes = readFileSync(FILE_PATH);

// v9: remarkable() is async
const api = await remarkable(token);

// ── Resolve target folder id ──────────────────────────────────────────────────
let parentId = ""; // "" = root

if (REMARKABLE_FOLDER_ID) {
  parentId = REMARKABLE_FOLDER_ID;
  console.error(`  Using folder id directly: ${parentId}`);

} else if (FOLDER_NAME) {
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

// ── Upload ────────────────────────────────────────────────────────────────────
let entry;
if (FILE_TYPE === "epub") {
  entry = await api.putEpub(DOC_NAME, fileBytes, { parent: parentId });
  console.error(`  Uploaded ePub: "${DOC_NAME}"`);
} else {
  entry = await api.putPdf(DOC_NAME, fileBytes, { parent: parentId });
  console.error(`  Uploaded PDF: "${DOC_NAME}"`);
}

console.log(JSON.stringify({ id: entry.id, hash: entry.hash, name: DOC_NAME, parentId }));

// ── Helpers ───────────────────────────────────────────────────────────────────

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
          return null;
        }
      })
    );
    results.push(...metas.filter(Boolean));

    const folders = results.filter((r) => r.type === "CollectionType");
    if (FOLDER_NAME && _pathResolvable(folders, FOLDER_NAME.replace(/^\//, "").split("/").filter(Boolean))) {
      console.error(`  Found all needed folders after scanning ${i + batch.length}/${ids.length} items.`);
      break;
    }
  }
  return results;
}

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
