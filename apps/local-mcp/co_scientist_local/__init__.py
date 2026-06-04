"""co-scientist-local: MCP server for Claude Code that writes to Firestore + Storage.

In v0 the backend is pluggable: an InMemoryBackend is used by tests, and a
FirestoreBackend (stub) will be added when Firebase deployment lands.
"""
