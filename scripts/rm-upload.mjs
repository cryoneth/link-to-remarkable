#!/usr/bin/env node
/**
 * Upload a PDF to reMarkable Cloud and move it to a target folder.
 * Mirrors the upload logic from telegram-monitor/remarkable-daily.js.
 *
 * Env vars:
 *   TOKEN_FILE   — path to the device token file
 *   DOC_NAME     — visible name on the tablet
 *   PDF_PATH     — local path to the PDF file
 *   FOLDER_NAME  — reMarkable folder name (e.g. "Articles/Inbox")
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

const api = remarkable(token);

// ── 1. List items (with retry) ────────────────────────────────────────────
let items;
let retries = 2;
while (retries >= 0) {
  try {
    items = await api.listItems();
    break;
  } catch (err) {
    if (retries === 0) {
      console.error(`listItems failed: ${err.message}`);
      process.exit(1);
    }
    console.error(`  Cloud busy, retrying listItems (${retries} left)...`);
    retries--;
    await new Promise((r) => setTimeout(r, 2000));
  }
}

// ── 2. Find target folder ─────────────────────────────────────────────────
let folderId = "";
if (FOLDER_NAME) {
  // Support nested paths: "Articles/Inbox" → find "Inbox" inside "Articles"
  const parts = FOLDER_NAME.replace(/^\//, "").split("/").filter(Boolean);
  let parentId = "";
  for (const part of parts) {
    const match = items.find(
      (i) => i.type === "CollectionType" && i.visibleName === part && i.parent === parentId
    );
    if (!match) {
      console.error(`  Warning: folder "${part}" not found (path: ${FOLDER_NAME}). Uploading to root.`);
      folderId = "";
      break;
    }
    parentId = match.id;
    folderId = match.id;
  }
  if (folderId) {
    console.error(`  Target folder: ${FOLDER_NAME} (${folderId})`);
  }
}

// ── 3. Upload PDF ─────────────────────────────────────────────────────────
const entry = await api.uploadPdf(DOC_NAME, pdfBytes);
console.error(`  Uploaded: ${DOC_NAME}`);

// ── 4. Move to folder (with retry) ───────────────────────────────────────
if (folderId) {
  let moveRetries = 3;
  while (moveRetries > 0) {
    try {
      await api.move(entry.hash, folderId);
      console.error(`  Moved to: ${FOLDER_NAME}`);
      break;
    } catch (err) {
      moveRetries--;
      if (moveRetries === 0) {
        console.error(`  Move failed after retries: ${err.message}`);
        // Don't fail the process — file is uploaded, just in root
        break;
      }
      console.error("  Cloud sync pending... retrying move in 2s");
      await new Promise((r) => setTimeout(r, 2000));
      const updatedItems = await api.listItems();
      const updatedEntry = updatedItems.find((i) => i.id === entry.id);
      if (updatedEntry) entry.hash = updatedEntry.hash;
    }
  }
}

// ── 5. Output result ──────────────────────────────────────────────────────
console.log(JSON.stringify({ id: entry.id, hash: entry.hash, name: DOC_NAME }));
