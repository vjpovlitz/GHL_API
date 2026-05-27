"""Shared DB connection + cached query helper for the Streamlit dashboard."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pyodbc
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _conn_str() -> str:
    server = os.getenv("GHL_SQL_SERVER", "localhost,1433")
    user = os.getenv("GHL_SQL_USER", "sa")
    pw = os.getenv("GHL_SQL_PASSWORD", "GhlDev_PassW0rd!")
    db = os.getenv("GHL_SQL_DATABASE", "ghl_warehouse")
    return (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={server};"
        f"UID={user};PWD={pw};DATABASE={db};"
        f"TrustServerCertificate=yes;Encrypt=no;"
    )


@st.cache_resource
def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(_conn_str(), autocommit=True)


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a SQL query, return a DataFrame. Cached 5 min."""
    return pd.read_sql(sql, get_connection(), params=params)
