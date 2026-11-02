"""Webhook activation intentionally unavailable in SS-RESEARCH-0.2.

No HTTP route is registered: do not acknowledge jobs before durable persistence.
A future receiver needs signed raw-body verification, delivery dedupe, scope checks,
and durable enqueue before acknowledgement. See docs/contracts/research-v0.2.md.
Only the signature/replay checks exist so far, unmounted, in services/api/linear_signature.py.
"""


async def linear_webhook(*args, **kwargs):
    raise RuntimeError("Linear webhook disabled; durable enqueue is not implemented")
