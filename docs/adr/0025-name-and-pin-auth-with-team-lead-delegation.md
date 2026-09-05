# ADR 0025: Name and PIN authentication with Team Lead delegation

> **Status: Accepted (Supersedes ADR 0024)**

## Context

ADR 0024 used shared Desk accounts and an honesty-based Volunteer Roster to avoid password overhead and desk lockouts. However, trust operations require accountable, first-class identity for prize distribution, team supervision, and granular auditing without the friction of complex passwords or email addresses.

## Decision

1. **Authentication by Name and 4-digit PIN**:
   - All email and password requirements are retired across the platform.
   - Authentication requires a unique normalized Name and a 4-digit PIN.
   - Initial bootstrap account is `name: "admin"` with PIN from `ADMIN_BOOTSTRAP_PIN`. The repository-known PIN `1234` is not a production fallback. The seeded Admin is marked `must_change_pin`.

2. **Delegated Account Provisioning**:
   - Admins can provision accounts for any role (`admin`, `team_lead`, `volunteer`, `clinical_desk_operator`).
   - Team Leads can provision `volunteer` accounts under their supervision (`team_lead_id` bound to the creator).
   - All new accounts receive default PIN `1234`.

3. **PIN Lifecycle & Safeguards**:
   - Until `must_change_pin` is false, the API permits only identity lookup, PIN change, and logout. The UI modal is not the authorization boundary.
   - 5 consecutive failed attempts lock the account for 15 minutes.
   - Team Leads can reset their assigned volunteers' PIN back to `1234` at any time; Admins can reset any user's PIN.

4. **Shift Handover**:
   - Desks feature a "Switch Volunteer" action in the header that clears the active session and presents an autofocused Name + PIN login prompt, keeping shift transitions under 5 seconds.

5. **Leaderboard & Team Rewards**:
   - Attribution is linked directly to the authenticated user ID (`created_by`, `arrived_by`).
   - The Leaderboard renders two distinct tables:
     - **Volunteers Table**: Individual volunteers ranked by their personal registrations and arrival scans.
     - **Team Leads Table**: Team Leads ranked strictly by the sum of points earned by all volunteers assigned to them (`team_lead_id`).

## Consequences

- Shared Desk accounts and the Volunteer Roster headers/endpoints are deprecated.
- Team Leads have autonomous control over their volunteer roster on a dedicated `/team` management page.
- Team Leads are rewarded based on the collective performance of their team rather than competing against volunteers for desk throughput.
- Identity and attribution are verified per action while remaining field-operable on camp laptops.

## Considered Options

- **Desk accounts with roster attribution (ADR 0024)**: Rejected because it prevented team lead delegation, lacked verified per-action accountability, and could not easily support team-level leaderboard aggregations.
- **Email/password per volunteer**: Rejected because 100+ volunteers in field conditions cannot manage passwords and emails without causing desk halts.
