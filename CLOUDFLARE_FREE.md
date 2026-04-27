# Cloudflare on the Free Plan — secure setup for the Whisper web tool

You **do not** need a paid Cloudflare plan to run this securely. The Free plan plus the
Free **Zero Trust** plan together give you a setup that is, for a single colleague, as
strong as paid options. This document explains what's included, what's not, and exactly
what to enable.

> TL;DR: Cloudflare **Tunnel** + Cloudflare **Access** (with email-OTP) + the app's own
> password + HTTPS = a strong free stack. The only meaningful trade-off is the **100 MB
> upload cap** per HTTP request.

---

## 1. What's free vs paid (April 2026)

| Feature | Free | Notes |
| --- | :---: | --- |
| Cloudflare DNS + universal HTTPS | ✅ | Auto-renewed certs, no cost ever. |
| **Cloudflare Tunnel** (`cloudflared`) | ✅ | No public IP, no inbound port. The whole point of this deployment. |
| **Cloudflare Access** (Zero Trust) | ✅ | Up to **50 users free**. Email-OTP, Google/GitHub/SSO, identity-based gating. |
| Always-on DDoS protection | ✅ | Layer 3/4/7. No config needed. |
| Bot-fight mode (basic) | ✅ | Toggle in dashboard. |
| Custom WAF rules (firewall rules) | ✅ | Up to 5 rules on Free, evaluated before app sees the request. |
| Rate limiting | ✅ (limited) | Free tier: 10K rule executions / month. Enough for a 1-user tool. |
| WAF Managed Rulesets (OWASP, Cloudflare Managed) | ❌ | Pro / Business only. Not critical when Access gates everything. |
| Request body cap | **100 MB** | Hard cap on Free. Pro = 200 MB. Business = 500 MB. **The one real limitation.** |
| Long-lived requests / SSE streams | ✅ | Tunnel does not impose an SSE timeout when heartbeats arrive (server sends them every 15s). |

---

## 2. Recommended free-plan security stack

Five layers, each free, each independent. An attacker has to break **all** of them.

```
Internet
   │
   ▼
┌───────────────────────────────────────────────┐
│ 1. Cloudflare edge (DDoS, TLS, WAF, bot)      │  ← free, automatic
└───────────────────────────────────────────────┘
   │
   ▼
┌───────────────────────────────────────────────┐
│ 2. Cloudflare Access (email OTP / SSO)        │  ← free Zero Trust, up to 50 users
└───────────────────────────────────────────────┘
   │
   ▼ (only authenticated colleague reaches here)
┌───────────────────────────────────────────────┐
│ 3. Cloudflare Tunnel — outbound only          │  ← no inbound port, no public IP
└───────────────────────────────────────────────┘
   │
   ▼
┌───────────────────────────────────────────────┐
│ 4. App-level password (HMAC-signed cookie)    │  ← second factor
└───────────────────────────────────────────────┘
   │
   ▼
┌───────────────────────────────────────────────┐
│ 5. Bind to 127.0.0.1 only                     │  ← LAN can't reach it either
└───────────────────────────────────────────────┘
```

---

## 3. Step-by-step (what to actually click)

Assumes you have already set up Cloudflare Tunnel per [DEPLOYMENT.md §4](DEPLOYMENT.md).

### 3.1 Enable Cloudflare Access (the most important step)

Cloudflare Access sits between the public internet and your Tunnel. Anyone hitting
`https://whisper.example.com` must prove they're your colleague **before** the request
reaches your Linux PC.

1. Cloudflare dashboard → **Zero Trust** (sidebar). If first time, accept the Free plan.
2. **Settings** → **Authentication** → make sure **One-time PIN** is enabled. (No setup
   required; uses email.) Optionally add **Google / GitHub / Microsoft** as identity
   providers for SSO.
3. **Access** → **Applications** → **Add an application** → **Self-hosted**.
   - **Application name**: `Whisper`
   - **Session duration**: `24 hours` (or what you prefer)
   - **Application domain**: `whisper.example.com`
   - Click **Next**.
4. **Add policy**:
   - **Policy name**: `Allow colleague`
   - **Action**: `Allow`
   - **Configure rules** → **Include** → **Emails** → enter your colleague's email
     (and your own). Add multiple emails if needed.
   - Click **Next**.
5. **Application appearance** — leave defaults. Click **Add application**.

That's it. Now opening `https://whisper.example.com` shows a Cloudflare login page first.
The colleague enters their email, gets a one-time PIN, types it, and only then sees the
app's sign-in screen.

### 3.2 Force HTTPS

Should already be on by default, but verify:

- Cloudflare dashboard → your zone → **SSL/TLS** → **Edge Certificates** → ensure
  **Always Use HTTPS** is **On**.
- **SSL/TLS** → **Overview** → encryption mode = **Full (strict)**. (Tunnel automatically
  presents a valid cert to Cloudflare, so strict mode works.)

### 3.3 Enable Bot Fight Mode

- Dashboard → **Security** → **Bots** → **Bot Fight Mode** → **On**.

This blocks obvious bots/scrapers at the edge for free. No false-positive risk for a
private tool with one user.

### 3.4 Add WAF rules (free, up to 5)

Go to **Security** → **WAF** → **Custom rules** → **Create rule**. Useful free rules for
this use case:

#### Rule A — block everything outside your country (optional but cheap)

If your colleague is in one country, block the rest of the world entirely:

```
Field:    Country
Operator: does not equal
Value:    DE     (or wherever you are)
Action:   Block
```

This wipes out 95 %+ of internet noise before Access even runs.

#### Rule B — block known datacenter ASNs (optional)

```
Field:    AS Num
Operator: is in
Value:    13335  16509  14618  15169    (Cloudflare, AWS, Amazon, Google — yes, blocking
                                          Cloudflare/Google ASNs blocks proxies/VPS users
                                          on those clouds, which is usually fine)
Action:   Managed Challenge
```

Skip this if your colleague uses a corporate VPN that hits one of these ASNs.

#### Rule C — rate-limit the login endpoint

Cloudflare's free Rate Limiting tier covers small workloads.

- Dashboard → **Security** → **WAF** → **Rate limiting rules** → **Create rule**.
- Name: `Throttle login`
- If: `URI Path equals /api/login`
- When rate exceeds: `5 requests per 1 minute per IP`
- Action: `Block` for `1 hour`.

Belt-and-braces — the app already hand-throttles login with a 0.5s sleep on failure.

### 3.5 (Optional) Service Auth tokens for scripted access

If you ever want to call the API from a script (no browser to do email-OTP):

- Zero Trust → **Access** → **Service Auth** → **Service Tokens** → create token.
- Bind to your application via a policy with **Service Auth** include rule.
- Use the token's `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers in your
  script.

Not needed for the colleague-only browser workflow.

---

## 4. The 100 MB upload cap — workarounds

This is the **only** real Free-plan limitation for this tool. Each HTTP request body is
capped at 100 MB at Cloudflare's edge. The app on the host can accept far more, but
Cloudflare blocks the upload before it gets there.

### How big is 100 MB of audio?

Approximate ceilings at 100 MB:

| Format | Bitrate | ≈ Length at 100 MB |
| --- | --- | --- |
| `.wav` (PCM 16-bit, 44.1 kHz, stereo) | ~1411 kbps | ~10 minutes |
| `.mp3` (192 kbps) | 192 kbps | ~70 minutes |
| `.m4a` (AAC 128 kbps) | 128 kbps | ~105 minutes |
| `.m4a` (AAC 64 kbps, mono — fine for speech) | 64 kbps | ~210 minutes |
| `.opus` (32 kbps mono — speech-optimized) | 32 kbps | ~7 hours |

**Practical recipe**: pre-convert recordings to mono AAC 64 kbps `.m4a`. Whisper
transcription quality is unaffected; voice falls in 80 Hz–8 kHz, far below the limit of
even 32 kbps Opus.

```bash
# Mono 64 kbps AAC (~5–10× smaller than the source, transparent for speech)
ffmpeg -i input.wav -ac 1 -c:a aac -b:a 64k output.m4a
```

For a colleague who isn't comfortable with `ffmpeg`, a small wrapper script is enough:

```bash
#!/usr/bin/env bash
# compress-for-upload.sh
ffmpeg -i "$1" -ac 1 -c:a aac -b:a 64k "${1%.*}.m4a"
```

### If you cannot pre-compress

Three escape hatches, in order of preference:

1. **Upgrade to Cloudflare Pro** ($25 / month). Body cap rises to 200 MB. One-click in
   dashboard. Still keeps Tunnel + Access + everything else.
2. **Bypass Cloudflare for uploads**: expose a second hostname (e.g. `upload.example.com`)
   with the orange cloud **off** (DNS only). Browser uploads go directly to your host's
   public IP. *This requires a public IP and inbound port — defeats the whole "no public
   IP" benefit, so only do it if you really must.*
3. **Add chunked upload to the app**: split the file client-side into <100 MB chunks,
   reassemble on the server. Not implemented yet — happy to add it if you hit this often.

For a single colleague transcribing meetings, **(1) pre-compress** covers virtually
every case.

---

## 5. What you do *not* need to pay for

For this specific workload (one colleague, audio transcription), you can confidently skip:

- **Cloudflare Pro / Business / Enterprise** — only worth it if you hit the body cap a lot.
- **WAF Managed Rulesets** — they protect against generic web vulns. Access already
  blocks unauthenticated traffic, and the app has a tiny attack surface (one upload
  endpoint, one login endpoint).
- **Argo Smart Routing** — irrelevant for a Tunnel.
- **Workers / Pages** — not needed.
- **Load Balancing** — single host, single user.

---

## 6. Verifying the setup

After enabling Access, confirm the gate is working:

```bash
# This should now redirect to a Cloudflare login page (HTTP 302), NOT your app's HTML.
curl -sI https://whisper.example.com | head -1
# HTTP/2 302
```

```bash
# Without a Cloudflare auth cookie, the API is unreachable too:
curl -i https://whisper.example.com/api/health
# Expect: HTTP/2 302   location: https://<team>.cloudflareaccess.com/...
```

The host's port 8000 should remain unreachable from outside:

```bash
# From any external network — should fail (connection refused / timeout).
nmap -p 8000 <your-host-public-ip>      # if you even know it
```

---

## 7. Summary checklist

- [ ] Tunnel running (`systemctl status cloudflared`).
- [ ] App on `127.0.0.1:8000` only (`systemctl status whisper-web`).
- [ ] DNS hostname proxied via Cloudflare (orange cloud).
- [ ] Cloudflare Access application + policy configured for colleague's email.
- [ ] SSL/TLS mode = Full (strict). Always Use HTTPS = On.
- [ ] Bot Fight Mode = On.
- [ ] WAF country-block rule (optional but recommended).
- [ ] Rate-limit on `/api/login` (5 req/min/IP).
- [ ] `WHISPER_PASSWORD` strong + unique. `WHISPER_SECRET_KEY` random 64 hex chars.
- [ ] `.env` permissions: `chmod 600 .env`.
- [ ] Pre-compression workflow understood for files >100 MB.

If all eight boxes above are ticked, you have a setup that is meaningfully more secure
than most paid SaaS deployments — at $0/month.
