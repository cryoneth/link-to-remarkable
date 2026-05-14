#!/usr/bin/env node
/**
 * Register this device with reMarkable Cloud.
 * Called by link2rm/remarkable.py on first run.
 *
 * Env vars:
 *   REG_CODE    — 8-letter one-time code from my.remarkable.com/device/desktop/connect
 *   TOKEN_FILE  — path to write the device token
 */
import { register } from "rmapi-js";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";

const { REG_CODE, TOKEN_FILE } = process.env;

if (!REG_CODE || !TOKEN_FILE) {
  console.error("rm-register: REG_CODE and TOKEN_FILE env vars are required");
  process.exit(1);
}

try {
  const token = await register(REG_CODE.trim());
  mkdirSync(dirname(TOKEN_FILE), { recursive: true });
  writeFileSync(TOKEN_FILE, token, "utf-8");
  console.error(`Registered. Token saved to ${TOKEN_FILE}`);
} catch (err) {
  console.error(`Registration failed: ${err.message}`);
  process.exit(1);
}
