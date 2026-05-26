# Regret + Fingerprint + Slow Harm v1 — G007

**연계**: FINAL_GOAL.md v2.3 §5.5 Slow Harm Safety · §6 데이터 모델 · §10 DoD
**구현**: `regret/scheduler.py` · `regret/fingerprint.py` · `regret/slow_harm.py` · `regret/accuracy.py` · `tests/test_regret_fingerprint.py` (14/14 green)

## 모듈
- **RegretReminder + record_regret_score**: 24h 후 회고 알림 schedule + RegretScore INSERT (0-10 CHECK)
- **FingerprintBuilder + update_fingerprint_snapshot**: 누적 corpus(AvoidanceSession+ProbeAnswer) → 통계(session/regret/decision)+ top tokens + 16-dim hash embedding (v2에서 sentence-transformers로 교체)
- **SlowHarmMonitor + build_weekly_snapshot**: 주별 SafetyHarmTimeSeries (self_blame · identity_failure · failure_imagery_ratio · pre_card_tension)
- **record_card_accuracy + record_return_intent**: CCG R2 권고 메트릭 — 1-5 self-rating → EvaluationResult INSERT (pass=accuracy≥4 또는 intent≥4)

## 다음 의존
- G008 MVPRelease — 알림 push 실제 구현 (현재 schedule만)
- G009 v2 — LLM-as-judge가 RegretScore와 carriers EvaluationResult 결합 활용
