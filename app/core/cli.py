import subprocess
import sys


def migrate():
    """Apply all pending migrations."""
    subprocess.run(["alembic", "upgrade", "head"], check=True)


def migration():
    """Create a new migration - usage: poetry run migration 'your message'."""
    msg = sys.argv[1] if len(sys.argv) > 1 else "auto migration"
    subprocess.run(
        ["alembic", "revision", "--autogenerate", "-m", msg],
        check=True,
    )


def downgrade():
    """Rollback one migration."""
    subprocess.run(["alembic", "downgrade", "-1"], check=True)


def new_resource():
    """Generate a new API resource (model, schema, repository, service, router)."""
    from app.core.generators.new_resource import run

    args = sys.argv[1:]
    name = None
    fields = None
    i = 0
    while i < len(args):
        if args[i] == "--fields" and i + 1 < len(args):
            fields = args[i + 1]
            i += 2
            continue
        if not args[i].startswith("-"):
            name = args[i]
            i += 1
            continue
        i += 1
    if not name:
        print("Usage: poetry run new-resource <name> [--fields 'field:type,...']")
        print("Example: poetry run new-resource product --fields 'name:str,description:str|None'")
        sys.exit(1)
    run(name, fields)
