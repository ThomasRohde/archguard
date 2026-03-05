# Security

## Threat model

guardrails-cli is a local CLI tool that reads/writes files on the local filesystem. It does not expose network services.

## Security considerations

- **stdin input**: All write commands accept JSON from stdin. Input is validated via Pydantic before any persistence. Malformed input is rejected with exit code 20.
- **SQLite**: Used as a local index. No user-supplied SQL. All queries use parameterized statements.
- **File paths**: The `--data-dir` option controls where files are read/written. No path traversal is possible beyond the specified directory.
- **No secrets**: This tool does not handle credentials, tokens, or secrets.
- **No network access**: After `init` (which downloads the embedding model), the tool operates fully offline.

## Reporting vulnerabilities

TODO: Define a security contact or process for reporting vulnerabilities.
  Why it matters: Even local tools can have injection or path traversal issues.
  How to fill this in: Specify an email address or link to a security policy.
