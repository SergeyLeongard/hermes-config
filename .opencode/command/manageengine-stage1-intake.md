---
description: Start focused mail intake implementation workflow
---

# ManageEngine Mail Dispatcher Window

Use this command in a separate chat window for mail intake implementation only.

## Scope

1. Implement Exchange/IMAP mail adapter into existing dispatcher core.
2. Do not change Telegram dispatcher business logic unless required for shared core.
3. Keep production-safe fallback requester: `sadmin`.

## Required Rules

1. Parse `Message-ID`, `In-Reply-To`, `References`, `From`, `Subject`, `Body`.
2. If reply-thread maps to request, update existing request.
3. If no mapping found, create new request.
4. Treat mail channel as IT by default (minimal pre-gate).
5. Do not send response back to mailing list.
6. Send processing result to Telegram incidents room 3 with standard 5-line format.

## Source of Truth

1. `docs/tz/manageengine-telegram-monitor-TECH_SPEC.md` section 47.
2. Server roadmap: `/home/sadmin/.hermes/skills/manageengine-fsm/manageengine-telegram-monitor-ROADMAP.md` (primary source).

## Note

1. Local `docs/tz/manageengine-telegram-monitor-ROADMAP.md` is a mirror copy only.

## Execution Rules

1. If any update to `TECH_SPEC` or `ROADMAP` is needed, warn and explain first before editing.
2. If implementation details are unclear or blocked, ask targeted questions before making risky assumptions.
