"""Webhook activation intentionally unavailable in SS-RESEARCH-0.2.

No HTTP route is registered: do not acknowledge jobs before durable persistence.
A future receiver needs signed raw-body verification, delivery dedupe, scope checks,
and durable enqueue before acknowledgement. See docs/contracts/research-v0.2.md.
"""


async def linear_webhook(*args, **kwargs):
    raise RuntimeError("Linear webhook disabled; durable enqueue is not implemented")
