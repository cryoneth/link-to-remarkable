#!/usr/bin/env node
/**
 * Upload a PDF to reMarkable Cloud.
 * Uses rmapi-js v9 — remarkable() is async; putPdf() accepts a parent folder id
 * so no separate move() call is needed.
 *
 * Env vars:
 *   TOKEN_FILE   — path to the device token file
 *   DOC_NAME     — visible name on the tablet
 *   PDF_PATH     — local path to the PDF file
 *   FOLDER_NAME  — reMarkable folder path (e.g. "Articles/Inbox" or "/Articles/Inbox")
 *                  use "" or omit to upload to root
 *
 * Writes JSON to stdout: {"id": "...", "hash": "...", "name": "..."}
 * Writes progress/errors to stderr.
 */
import { remarkable } from "rmapi-js";
import { readFileSync } from "node:fs";

const { TOKEN_FILE, DOC_NAME, PDF_PATH, FOLDER_NAME } = process.env;

if (!TOKEN_FILE || !DOC_NAME || !PDF_PATH) {
  console.error("rm-upload: TOKEN_FILE, DOC_NAME, and PDF_PATH are required");
  process.exit(1);
}

const token = readFileSync(TOKEN_FILE, "utf-8").trim();
const pdfBytes = readFileSync(PDF_PATH);

// v9: remarkable() is async
const api = await remarkable(token);

// ── 1. List items to find target folder id ────────────────────────────────
const items = await api.listItems();
console.error(`  Sync complete. Found ${items.length} total items.`);

// ── 2. Resolve folder path → folder id ───────────────────────────────────
let parentId = ""; // "" = root
if (FOLDER_NAME) {
  const parts = FOLDER_NAME.replace(/^\//, "").split("/").filter(Boolean);
  let currentParentId = "";
  let found = true;

  for (const part of parts) {
    const match = items.find(
      (i) => i.type === "CollectionType"
          && i.visibleName === part
          && i.parent === currentParentId
    );
    if (!match) {
      console.error(`  Warning: folder "${part}" not found (path: ${FOLDER_NAME}). Uploading to root.`);
      found = false;
      break;
    }
    currentParentId = match.id;
  }

  if (found) {
    parentId = currentParentId;
    console.error(`  Target folder: ${FOLDER_NAME} (id: ${parentId})`);
  }
}

// ── 3. Upload PDF directly into the target folder ─────────────────────────
// putPdf() accepts { parent: id } so no separate move() is needed.
const entry = await api.putPdf(DOC_NAME, pdfBytes, { parent: parentId });
console.error(`  Uploaded: "${DOC_NAME}"`);

// ── 4. Output result ──────────────────────────────────────────────────────
console.log(JSON.stringify({ id: entry.id, hash: entry.hash, name: DOC_NAME }));
