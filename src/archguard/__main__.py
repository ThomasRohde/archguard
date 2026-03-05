"""Entry point for `python -m archguard` and the `guardrails` console script."""

from archguard.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
