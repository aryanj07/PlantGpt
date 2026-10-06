"""Rate Limit / Concurrency Module scaffold (plan Section D, F, ADR 9).
Phase 1, owner: Rimsha. Not wired into the Chat Module request path yet -
plan Section E step 5 (check before any LLM call) is where this plugs in."""


class RateLimiter:
    def check(self, *, tenant_id: str, user_id: str) -> bool:
        raise NotImplementedError(
            "Real Redis-backed token-bucket limiting lands in Phase 1 (plan ADR 9)."
        )
