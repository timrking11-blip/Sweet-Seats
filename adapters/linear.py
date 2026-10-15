"""Reserved Linear boundary. All network operations deferred in contract slice."""


class LinearClient:
    def __init__(self, *args, **kwargs):
        pass

    async def graphql(self, *args, **kwargs):
        raise RuntimeError("Live Linear GraphQL disabled pending verified scoped adapter")

    async def get_issue(self, *args, **kwargs):
        raise RuntimeError("Live Linear read disabled pending activation")

    async def open_issues_with_label(self, *args, **kwargs):
        raise RuntimeError("Live Linear sweep disabled pending activation")

    async def add_comment(self, *args, **kwargs):
        raise RuntimeError("Writeback disabled pending authenticated exact approval and durable outbox")
