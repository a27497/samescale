class ManagedSession:
    def __init__(self, transport: object) -> None:
        self.transport = transport
        self.closed = False

    def send(self, payload: str) -> str:
        if self.closed:
            raise RuntimeError("session is closed")
        return self.transport.send(payload)

    def close(self) -> None:
        if not self.closed:
            self.transport.close()
            self.closed = True

    def __enter__(self) -> "ManagedSession":
        if self.closed:
            raise RuntimeError("session is closed")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
