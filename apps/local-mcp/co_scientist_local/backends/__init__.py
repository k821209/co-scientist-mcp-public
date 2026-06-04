from .base import Backend, NotFound
from .memory import InMemoryBackend

# FirestoreBackend is exported lazily — `import firebase_admin` is only needed
# when the user actually constructs one. This keeps test environments light.
__all__ = ["Backend", "InMemoryBackend", "NotFound", "FirestoreBackend"]


def __getattr__(name: str):
    if name == "FirestoreBackend":
        from .firestore import FirestoreBackend
        return FirestoreBackend
    raise AttributeError(name)
