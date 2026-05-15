---
description: Start focused mail intake implementation workflow
---

# ManageEngine Mail Dispatcher Window

Use this command in a separate chat window for mail intake implementation only.

## Scope

1. Implement Exchange/IMAP mail adapter into existing dispatcher core.
2. Do not change Telegram dispatcher business logic unless required for shared core.
3. Keep production-safe fallback requester: `sadmin`.

## Operational Hosts

1. `10.251.0.55` is the mail server used to read inbox messages.
2. Dispatcher, sync, and other Hermes scripts must run on the Hermes server host.

## Required Rules

1. Parse `Message-ID`, `In-Reply-To`, `References`, `From`, `Subject`, `Body`.
2. If reply-thread maps to request, update existing request.
3. If no mapping found, create new request.
4. Treat mail channel as IT by default (minimal pre-gate).
5. Do not send response back to mailing list.
6. Send processing result to Telegram incidents room 3 with standard 5-line format.

## Source of Truth

1. `docs/tz/manageengine-telegram-monitor-TECH_SPEC.md` section 47.
2. `docs/tz/manageengine-telegram-monitor-ROADMAP.md` stage 1 mail intake item.
3. Unified identities: `skills/manageengine-fsm/user_mapping.json` (see `/manageengine-identity-mapping`).
