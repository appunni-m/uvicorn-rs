"""Shared report metadata for the unified coverage producer and validator."""

PENDING_COVERAGE_MCP_FOLLOW_UP = (
    "Query and fully paginate both regions and lines for this exact report; require zero missing "
    "source-span totals, source=matches_receipt, and tests=passed; retain function-instantiation "
    "groups as diagnostics."
)


def pending_coverage_mcp_request(measurement_path: str) -> dict[str, str]:
    """Build the one accepted pending Coverage-MCP request envelope."""
    return {
        "status": "awaiting_query",
        "measurement_path": measurement_path,
        "metric": "regions",
        "required_follow_up": PENDING_COVERAGE_MCP_FOLLOW_UP,
    }
