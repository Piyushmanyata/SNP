# ADR 0024: Desk accounts for auth, roster names for attribution

Amends ADR 0002 in scope: admin still creates every account, but volunteers no longer have one.

## Context

About a hundred non-technical volunteers staff ten Registration desks and the Fulfilment lines for five thousand patients a day. With laptops as desks, a login per volunteer means a hundred passwords on paper and a logout and login at every shift change, at the desk with the queue in front of it. A volunteer locked out at nine in the morning with no admin nearby stops a desk.

The trust gives prizes to the best-performing volunteers, so the app must still count registrations per person.

## Decision

- Authentication is per desk. A Desk account is signed in once in the morning by a team lead and shared by everyone who sits there. Team leads and admins keep personal accounts because Mismatch review confirmation and Print window changes need a real name.
- Attribution is per person through the Volunteer roster. A volunteer picks their name when they sit down; that On-desk volunteer rides on every posting until hand-over. A desk with nobody picked refuses to post.
- No PIN, no password, no verification of the pick. The prize is small enough that honesty suffices.

## Consequences

No volunteer ever sees a password. Shift change is a chair swap and a name pick. The leaderboard survives on roster names. Attribution is honesty-based, so it is a prize signal, not an audit trail; the audit trail is the Desk account plus the paper roster. Audit questions that need a person behind a desk action are answered by asking who was on that desk at that time.

## Rejected alternatives

- One account per volunteer — verified attribution, but a hundred passwords and a lockout risk at the desk.
- Desk account with a PIN per volunteer — verifies the pick, but it is a password by another name and brings the lockout back.
- Desk account with no attribution at all — simplest, but the trust cannot give prizes.
