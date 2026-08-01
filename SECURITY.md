# Security notes

## Credential rotation required

An OpenSSH private key was previously committed as `itproger/y`. The file is now
ignored and removed from the current Git index, but it remains available in older
commits until repository history is rewritten.

Before the next deployment:

1. revoke the old public key on every server where it was authorized;
2. generate a new key pair outside the repository;
3. provide its path through deployment configuration or a secret manager;
4. rewrite Git history in a coordinated maintenance window, then force-push and
   have every contributor re-clone the repository.

Never commit private keys, `.env` files, databases or user uploads.

## Reporting

Report suspected credential exposure directly to the system owner. Do not include
passwords, private keys or production data in an issue tracker.
