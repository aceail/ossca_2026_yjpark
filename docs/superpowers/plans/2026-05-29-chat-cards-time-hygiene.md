# Chat Cards + Time Hygiene Plan (Sprint 40)

> Subagent-driven execution of [the design spec](../specs/2026-05-29-chat-cards-time-hygiene-design.md).

7 tasks covered as commits on `feature/sprint-40-chat-cards-time`:

| Task | Commit | Files |
|---|---|---|
| T1 deterministic time parse | 6ea1fd9 | pipeline/time_parse.py + 12 tests |
| T2 chat card JSON post-process + time override | d405452 | pipeline/chat.py + 4 tests |
| T3 RecoveryCardCluster + chat integration | 082bf39 | frontend/components/RecoveryCardCluster.tsx, globals.css card-mount keyframe, chat/page.tsx CARD_PREFIXES extension |
| T4 verbatim time hint with task deadlines | 2bad9dc | pipeline/chat.py _build_temporal_hints + pipeline/orchestrator.py |
| T5 interactive action cards | 10ce4b3 | chat/page.tsx button wrap + cardDeepLink + → affordance |
| T6 motion (already inlined in T3+T5) | — | card-mount + active:scale-[0.97] + prefers-reduced-motion |
| T7 SW bump + redeploy + patch | this commit | sw.js v22 → v23 |
