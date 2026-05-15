---
description: Maintain unified identity mapping for Telegram, email, and SDP users
---

# ManageEngine Identity Mapping

Use this command for one source of truth of user identities.

## Source of Truth

1. `skills/manageengine-fsm/user_mapping.json`

## Operational Hosts

1. `10.251.0.55` is the mail server (EWS/IMAP source), not the Hermes app host.
2. Run Hermes scripts (for example `identity_auto_sync.py`) on the Hermes server host only.

## Model

1. One identity links: `requester_id`, `telegram_user_id`, `telegram_username`, `email`.
2. `requester_id` is the canonical key.
3. `status` must be `confirmed` before production usage.

## Resolution Rules

1. Telegram channel: match by `telegram_user_id`.
2. Mail channel: match by `email`.
3. If not found: fallback requester `sadmin`.

## Update Policy

1. Add new pairs as `candidate` first.
2. Promote to `confirmed` only after support-team validation.
3. Keep `mapping.by_telegram_user_id` and `mapping.by_email` aligned with `identities` records.
