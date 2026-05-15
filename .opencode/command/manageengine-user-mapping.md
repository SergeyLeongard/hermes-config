---
description: Start focused user mapping workflow
---

# ManageEngine User Mapping Window

Use this command in a separate chat window for user mapping tasks only.

## Scope

1. Work on unified identity mapping: `telegram <-> email <-> requester`.
2. Do not change triage logic unless explicitly requested.
3. Keep production-safe fallback: unknown user -> `sadmin`.

## Source of Truth

1. Server roadmap: `/home/sadmin/.hermes/skills/manageengine-fsm/manageengine-telegram-monitor-ROADMAP.md`.
2. Tech spec: `docs/tz/manageengine-telegram-monitor-TECH_SPEC.md` sections 44-45.
3. Unified mapping file: `skills/manageengine-fsm/user_mapping.json`.

## Required Behavior

1. Match by `telegram_user_id` first for Telegram channel.
2. Match by `email` first for Mail channel.
3. If not found in mapping, fallback to SDP lookup (for email), then `sadmin`.
4. Always include UDF `IDUserTelegram` in created requests.

## Current Confirmed Mappings

1. `@SergeyAL` -> requester `308` (`Сергей Леонгард`).
2. `216995471` / `@northmund95` -> requester `329` (`Нурберген Сауриков`).

## Daily Enrichment Rules

1. Collect candidate pairs from new requests once per day.
2. Mark new pairs as `candidate`, not `confirmed`.
3. Promote to `confirmed` only after support team validation.
