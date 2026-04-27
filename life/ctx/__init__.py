"""Context assembly — prompt surface for steward spawns.

sections.py — pure renderers, one per data slice. each returns a string or "".
assemble.py — compose sections into wake/chat/tg/auto prompts.
fragments.py — static prompt atoms (templates, constants).

callers:
- steward/wake.py prints assembled wake to stdout
- steward/chat.py uses assemble for --append-system-prompt directly
- daemon spawns capture wake via fetch_wake_context (subprocess)
"""
