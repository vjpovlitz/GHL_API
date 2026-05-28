"""Curated MCP tools, grouped by domain and collected into REGISTRY.

To add a tool:
  1. Write a function in the relevant module (or add a new module).
  2. Decorate it with @curated, give it type-hinted params and a model-facing
     docstring — the hints become the tool's input schema and the docstring
     becomes the description the model reads to decide when to call it.
  3. Make sure the module is imported below so the decorator runs at import.

server.py registers everything in REGISTRY with FastMCP.
"""
from . import analytics, contacts, conversations, opportunities  # noqa: F401
from .base import REGISTRY, curated

__all__ = ["REGISTRY", "curated"]
