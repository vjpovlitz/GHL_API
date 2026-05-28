"""DCR warehouse MCP server.

Exposes the dcr_warehouse (SQL Server) to an MCP host (LM Studio) as a set of
read-only query tools: curated view-backed tools, a guarded free-SQL tool, and
schema introspection. All DB access goes through a read-only login (dcr_ro).
"""

__version__ = "0.0.1"
