"""Reserved research boundary; no unverified SDK call or paid execution."""


async def run_research(*args, **kwargs):
    raise RuntimeError("Paid research disabled pending verified API, credentials and spending approval")
