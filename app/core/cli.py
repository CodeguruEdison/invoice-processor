import subprocess


def migrate():
    """Apply all pending migrations."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)


def migration():
    """Create a new migration - usage: poetry run migration 'your message'."""
    import sys

    msg = sys.argv[1] if len(sys.argv) > 1 else "auto migration"
    subprocess.run(
        ["alembic", "revision", "--autogenerate", "-m", msg],
        check=True,
    )


def downgrade():
    """Rollback one migration."""
    subprocess.run(["alembic", "downgrade", "-1"], check=True)
