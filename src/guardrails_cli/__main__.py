"""Entry point for `python -m guardrails_cli` and the `guardrails` console script."""

from guardrails_cli.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
