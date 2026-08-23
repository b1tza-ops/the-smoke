# Authentication foundation

The Smoke keeps bcrypt password hashing and adds a local, testable
foundation for email verification and password recovery.

## Passwords and tokens

- Passwords are stored only as bcrypt hashes.
- Verification and reset tokens are generated with the secrets module.
- Only SHA-256 token hashes are stored in the account_tokens table.
- Tokens have an expiry timestamp and a one-time used_at timestamp.
- Issuing a new token invalidates older unused tokens of the same type.

Raw tokens exist only long enough to be passed to a delivery callback.
Production email delivery is intentionally outside V1.

## Generic recovery response

Password-reset requests always return the same message, whether or not an
account exists for the supplied email address. This prevents the recovery
screen from exposing registered addresses.

## Rate-limit integration

Authentication services accept a rate-limiter interface. The repository
includes NullRateLimiter as the deployment-neutral default and
InMemoryRateLimiter for local development and tests.

A public multi-process deployment should provide a shared limiter backed by
Redis or another central store.

## Local testing

Tests inject a delivery callback that captures a raw token in memory. They can
then exercise reset or verification without sending email. The database is
checked to ensure that only the token hash was persisted.
