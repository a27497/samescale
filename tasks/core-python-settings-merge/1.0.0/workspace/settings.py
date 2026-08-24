class ManagedSession:
    def __init__(self, transport: object) -> None:
        self.transport = transport
        self.closed = False

    def send(self, payload: str) -> str:
        return self.transport.send(payload)

    def close(self) -> None:
        self.transport.close()
        self.closed = True

    def __enter__(self) -> "ManagedSession":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None
