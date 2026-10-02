"""MongoDB index initialization compatibility entry point."""

from app.database import initialize_mongodb


def run_lightweight_migrations(_database=None) -> None:
    """Create MongoDB indexes; collection creation is handled by MongoDB."""
    initialize_mongodb()
