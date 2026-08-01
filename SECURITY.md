# Security Policy

## Reporting a vulnerability

Please do not publish security vulnerabilities in a public issue.

Use GitHub private vulnerability reporting when it is available. Otherwise,
contact the repository owner privately through their GitHub profile. Include a
short description, reproduction steps and the affected component. Do not attach
credentials, private keys, personal data or production database contents.

## Secrets and local data

The repository must not contain:

- `.env` files with real configuration;
- private keys, passwords or access tokens;
- local databases and backups;
- user uploads, logs or generated runtime files.

Use `.env.example` to document configuration with placeholder values only. If a
secret is exposed, revoke it immediately and remove it from the complete Git
history before publishing the repository again.
