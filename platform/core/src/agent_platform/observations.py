"""Freshness contract for read-only workload and posture observations."""

FRESH_SECONDS = 120  # The observer scans every 15 seconds; older observations cannot support a current verdict.
