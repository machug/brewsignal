"""Supabase client utilities for cloud mode operations.

This module provides admin-level Supabase client access for operations
that require service role permissions, such as user metadata management.
"""

from functools import lru_cache
from typing import Optional

from supabase import create_client, Client

from .config import settings


@lru_cache(maxsize=1)
def get_supabase_admin() -> Optional[Client]:
    """Get Supabase client with service role key for admin operations.

    Returns:
        Supabase Client configured with service role key, or None if not configured.

    Note:
        The service role key bypasses Row Level Security (RLS) policies.
        Only use for admin operations like user metadata management.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None

    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key
    )


@lru_cache(maxsize=1)
def get_supabase_client() -> Optional[Client]:
    """Get Supabase client with anon key for regular operations.

    Returns:
        Supabase Client configured with anon key, or None if not configured.

    Note:
        This client respects RLS policies and should be used for
        standard data operations where user context applies.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        return None

    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key
    )
