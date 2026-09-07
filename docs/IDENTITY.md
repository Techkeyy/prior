# PRIOR durable identity (Phase 1)

Product promise: **Your PRIOR memory follows you, not your browser.**

## Model

```
Account --owns--> Workspace --contains--> Jobs / Lessons / Sibyl memory
```

The workspace abstraction is unchanged. Accounts only resolve to workspaces.

## Merge policy (hard rule)

- **First login claims the guest workspace.** Same workspace ID, same jobs,
  same lessons, zero data movement.
- **Returning accounts resolve to their owned workspace.** An unrelated
  guest workspace in the same browser is preserved untouched and surfaced
  as `pending_guest_workspace`. It is **never** merged automatically.
- **Identity key is `(provider, provider_subject)`.** Email alone never
  merges accounts across providers. Different provider subjects are
  different accounts, even with equal display names or emails.
- **Logout** revokes the session only. No data is deleted or mutated.

## Google sign-in (owner action required)

1. Open the Google Cloud Console and create (or reuse) a project.
2. Configure the OAuth consent screen (External user type is enough for the
   hackathon; add the owner account as a test user while the app is in
   testing mode).
3. Create Credentials -> OAuth client ID -> **Web application**.
4. Add this exact Authorized redirect URI:
   `https://prior.103-195-188-198.sslip.io/api/auth/google/callback`
5. Add this exact Authorized JavaScript origin:
   `https://prior.103-195-188-198.sslip.io`
6. Put the issued Client ID and Client secret into the server environment
   as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (never into chat or
   the repo). Redeploy.

Local development uses `http://127.0.0.1:<port>/api/auth/google/callback`;
add that URI too if local Google sign-in is ever needed.

## Email sign-in

Without an email provider, `/api/auth/email/start` still answers in the
same shape but reports `"delivery": "not_configured"` and no code is sent.
To enable real delivery, set:

```
EMAIL_PROVIDER=smtp
EMAIL_SMTP_HOST=<host>
EMAIL_SMTP_PORT=465
EMAIL_SMTP_TLS=ssl
EMAIL_SMTP_USER=<user, optional>
EMAIL_SMTP_PASSWORD=<secret>
EMAIL_FROM=<sender address>
```

Codes are 6 digits, 10-minute expiry, single-use, max 10 verify attempts,
max 5 sends per address per hour.

## Other environment

```
PRIOR_PUBLIC_URL=https://prior.103-195-188-198.sslip.io   # enables Secure cookies + correct OAuth redirect
PRIOR_SESSION_TTL_S=7776000                               # 90 days, sliding refresh
PRIOR_IDENTITY_DB=/opt/prior/data/identity.db             # defaults under PRIOR_DATA_DIR
PRIOR_COOKIE_SECURE=true                                  # normally inferred from the https public URL
```
