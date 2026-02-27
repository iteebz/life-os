class LifeError(Exception):
    pass


class NotFoundError(LifeError):
    pass


class ValidationError(LifeError):
    pass


class ConflictError(LifeError):
    pass


class StateError(LifeError):
    pass


class AmbiguousError(LifeError):
    def __init__(self, ref: str, count: int = 0, sample: list[str] | None = None):
        self.ref = ref
        self.count = count
        self.sample = sample or []
        count_note = f" ({count})" if count else ""
        note = f": {', '.join(self.sample)}" if self.sample else ""
        super().__init__(f"ambiguous ref '{ref}' matches multiple items{count_note}{note}")
