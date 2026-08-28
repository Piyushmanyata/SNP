# ADR 0002: Admin bootstrap creates once, never resets password

## Context

`seed_admin()` runs on FastAPI startup. If an admin document already existed, it compared `ADMIN_PASSWORD` to the stored hash and overwrote `password_hash` when they differed. Restarting the API (including every Docker restart) reset any password an operator had changed.

## Decision

Create the admin user when no document exists for `ADMIN_EMAIL`. If the user already exists, do nothing.

## Consequences

Existing MongoDB data, including admin credentials, is preserved across restarts. Changing the admin password is an explicit operator action, not a side effect of `ADMIN_PASSWORD` in the environment.

## Rejected alternatives

- Keep resetting to `ADMIN_PASSWORD` on startup — convenient for a demo box, destructive for any real database.
- Upsert the whole admin document — would clobber name/role/disabled state as well as the password.
