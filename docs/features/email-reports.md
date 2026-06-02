# Feature: Email Reports

**Source:** [`scripts/send_email.py`](../../scripts/send_email.py) ·
**CLI:** `atlas email`

A credential-free SMTP sender used by the report/newsletter skills. The app
password comes from the environment; **nothing is hardcoded**. It supports HTML +
plain-text bodies and file attachments.

---

## How it works

`send_email(to, subject, body_html=None, body_text=None, attachments=None)`:

1. Builds a `multipart/mixed` message. `From` is `"{SENDER_NAME} <{SENDER_EMAIL}>"`;
   `To` accepts a string or a list.
2. Bodies go in a `multipart/alternative` part — `body_text` as `text/plain` and
   `body_html` as `text/html` (provide at least one).
3. Each attachment that exists on disk is base64-encoded as an
   `application/octet-stream` part with a `Content-Disposition: attachment`
   filename. Missing paths print a warning and are skipped.
4. Connects to `SMTP_SERVER:SMTP_PORT`, upgrades with **STARTTLS** (not implicit
   SSL — port 587), logs in with `SENDER_EMAIL` + `SMTP_APP_PASSWORD`, and sends.

---

## Usage

For a quick message, `atlas email` takes flags:

```bash
atlas email --to me@example.com --subject "Daily report" --body "<h1>Hello</h1><p>…</p>"
atlas email -s "Daily report" -b "plain body" --text --attach /path/report.pdf
```

| Flag | Required | Notes |
|---|---|---|
| `--to` | no | recipient; defaults to `USER_EMAIL` |
| `--subject` / `-s` | **yes** | subject line |
| `--body` / `-b` | **yes** | HTML by default; add `--text` for plain text |
| `--text` | no | send `--body` as `text/plain` instead of HTML |
| `--attach` / `-a` | no | file to attach (repeatable) |

For a list of recipients, both body types, or a scripted payload, use `--json`
(the same shape `scripts/send_email.py` accepts directly as its argument):

```bash
atlas email --json '{
  "to": "me@example.com",
  "subject": "Daily report",
  "body_html": "<h1>Hello</h1><p>…</p>",
  "body_text": "Hello …",
  "attachments": ["/path/to/report.pdf"]
}'
```

| Field | Required | Notes |
|---|---|---|
| `to` | **yes** | string or list of addresses |
| `subject` | **yes** | |
| `body_html` | no | HTML body |
| `body_text` | no | plain-text body |
| `attachments` | no | list of absolute file paths |

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `SENDER_EMAIL` | `""` (**required**) | from address |
| `SMTP_APP_PASSWORD` | `""` (**required**) | app password / SMTP password |
| `SENDER_NAME` | `Atlas` | display name |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP host |
| `SMTP_PORT` | `587` | STARTTLS port |

For **Gmail**, generate an [app password](https://myaccount.google.com/apppasswords)
(requires 2-factor auth) — your normal account password won't work.
`SMTP_APP_PASSWORD` is **secret**: keep it in the environment, never in a note,
`SKILL.md`, or commit.

---

## Behaviour notes

- Missing `SMTP_APP_PASSWORD` or `SENDER_EMAIL` exits with code `1` and a setup
  hint.
- A **failed send returns `False` but still exits 0** — callers can't detect send
  failure from the exit code alone. `atlas doctor` / `atlas health` report whether
  SMTP is at least *configured* (both required vars present).
- Sending email is an outward-facing action — when testing manually, send to
  yourself first. The report skills call this for you.

See also: [skills-and-automation.md](skills-and-automation.md) ·
[`docs/SCRIPTS.md`](../SCRIPTS.md#send_emailpy)
