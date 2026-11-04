"""Allow ``python -m android_agent`` to run the CLI."""

from .cli import app

if __name__ == "__main__":
    app()
