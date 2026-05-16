# Android Share Target — Setup Handoff

Everything needed to continue. Pick up from step 1.

---

## Current state

- `link2rm` server runs automatically at Mac boot (launchd)
- Sends articles as ePub to reMarkable via the existing device token
- Server is at `http://127.0.0.1:8765` locally, not yet reachable from the phone
- reMarkable token: `~/.config/link2rm/rmapi-token`
- Server logs: `~/.link2rm/server.log`
- Project: `/Users/cryon/Documents/Coding/link-to-remarkable`

---

## Step 1 — Install Tailscale on the Mac

```bash
brew install --cask tailscale
```

Open Tailscale from the menu bar → Sign in (use Google or GitHub, pick one you'll also use on the phone) → Leave it running.

Find your Mac's Tailscale IP: click the Tailscale icon in the menu bar. It'll be something like `100.64.x.x`. Write it down.

**Verify the server is reachable over Tailscale:**
```bash
curl http://<your-tailscale-ip>:8765/health
# should return {"ok":true}
```

If it returns nothing, the Mac firewall might be blocking port 8765. Fix:
```bash
# Allow incoming connections on port 8765
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add $(which uv)
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblock $(which uv)
```

---

## Step 2 — Install Tailscale on the S24 Ultra

1. Play Store → search **Tailscale** → install
2. Open it → Sign in with the **same account** as the Mac
3. Your Mac should appear in the device list with its `100.x.x.x` IP
4. Toggle Tailscale on

Test from the phone browser: open `http://<mac-tailscale-ip>:8765/health` — should show `{"ok":true}`.

---

## Step 3 — Install HTTP Shortcuts on the S24 Ultra

Play Store → search **HTTP Shortcuts** (by Waboodoo) → install.

---

## Step 4 — Create the share shortcut

In HTTP Shortcuts:

1. Tap **+** → **Regular Shortcut**
2. **Basic settings:**
   - Name: `Send to reMarkable`
   - Icon: pick something recognisable
3. **HTTP request tab:**
   - Method: `POST`
   - URL: `http://<mac-tailscale-ip>:8765/ingest`
4. **Request body tab:**
   - Body type: `Custom text`
   - Content type: `application/json`
   - Body:
     ```json
     {"url": "{url}"}
     ```
5. **Response handling:**
   - Success output: `Simple toast` → message: `Sent to reMarkable ✓`
   - Failure output: `Simple toast` → message: `Failed: {error}`
6. **Save** the shortcut

**Enable share target:**
- Long-press the shortcut → **Place on home screen** (optional)
- In shortcut settings → **Trigger shortcuts via share menu** → toggle on → select **URL**

---

## Step 5 — Test end to end

1. Open any article in Chrome or Samsung Internet on the S24
2. Tap Share → scroll to **HTTP Shortcuts** → tap **Send to reMarkable**
3. Toast appears: `Sent to reMarkable ✓`
4. Article appears on the tablet as an ePub within ~30 seconds

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No toast / timeout | Tailscale not connected | Check Tailscale is on on both devices |
| `{"ok":true}` works in browser but share fails | Wrong URL in shortcut | Double-check the Tailscale IP |
| Article appears with no content | Page is JS-rendered | Server will try Playwright fallback automatically |
| Server not running after reboot | launchd service issue | `launchctl list \| grep link2rm` — if missing, re-run: `launchctl load ~/Library/LaunchAgents/com.cryoneth.link2rm.plist` |
| Want PDF instead of ePub | Format preference | Add `"format": "pdf"` to the shortcut body |

---

## What comes next (after this is working)

- **reMarkable reply pending:** waiting to hear if the Device Authorization Flow is enabled on their Auth0 app. If yes, the pipeline can send articles as native **notebooks** (fully annotatable) instead of ePubs — same extraction quality, better tablet experience.
- **Firefox Android extension:** a ~50-line extension that adds a toolbar button to Firefox for Android, pointing at the same server. Eliminates the need for the share sheet entirely.
- **Notebook format backend:** `src/link2rm/remarkable_cloud.py` — Auth0 token + `POST /import/v1/files` with `convert: true`. Already fully spec'd from reverse-engineering the Chrome extension source.

---

## Useful commands

```bash
# Check server is running
curl http://127.0.0.1:8765/health

# View live server logs
tail -f ~/.link2rm/server.log

# View strategy log (what got sent, which extractor was used)
cat ~/.link2rm/log.jsonl | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin]"

# Restart the server
launchctl unload ~/Library/LaunchAgents/com.cryoneth.link2rm.plist
launchctl load   ~/Library/LaunchAgents/com.cryoneth.link2rm.plist

# Send a test URL manually (from Mac)
uv run link2rm https://noahpinion.substack.com/p/answering-the-techno-pessimists-part

# Send as PDF instead of ePub
uv run link2rm --format pdf https://example.com/article
```
