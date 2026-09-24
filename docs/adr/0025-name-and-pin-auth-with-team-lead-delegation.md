# ADR 0025: Name and PIN authentication with Team Lead delegation

> **Status: Accepted (Supersedes ADR 0024)**

## Context

ADR 0024 used shared Desk accounts and an honesty-based Volunteer Roster to avoid password overhead and desk lockouts. However, trust operations require accountable, first-class identity for prize distribution, team supervision, and granular auditing without the friction of complex passwords or email addresses.

## Decision

1. **Authentication by Name and PIN** (amended by #50 S4):
   - All email and password requirements are retired across the platform.
   - Authentication requires a unique normalized Name and a PIN: 6 digits for Admins and Team Leads, who can export or act on every patient record; 4 digits for Volunteers and Clinical operators. `validate_pin_policy(pin, role)` also refuses one digit repeated and straight runs such as `1234` or `654321`.
   - Initial bootstrap account is `name: "admin"` with PIN from `ADMIN_BOOTSTRAP_PIN`, which must pass the Admin policy. The seeded Admin is marked `must_change_pin`.

2. **Delegated Account Provisioning**:
   - Admins can provision accounts for any role (`admin`, `team_lead`, `volunteer`, `clinical_desk_operator`).
   - Team Leads can provision `volunteer` accounts under their supervision (`team_lead_id` bound to the creator).
   - Each new account receives a random one-time PIN of its role's length (`secrets`), returned once in the create response and never stored in plain text. No default PIN exists.

3. **PIN Lifecycle & Safeguards**:
   - Until `must_change_pin` is false, the API permits only identity lookup, PIN change, and logout. The UI modal is not the authorization boundary.
   - A PIN change must differ from the current PIN and pass the role's policy.
   - 5 failed attempts for one Name within 15 minutes lock that Name for 15 minutes. A network (client address) where no one has signed in during the last 12 hours gets 50 attempts across all Names in 15 minutes. A successful sign-in marks its network trusted for 12 hours (`login_sources`), and a trusted network has no network budget, so a guest on the venue Wi-Fi cannot shut every desk out.
   - Every lockout is recorded (`login_lockouts`, kept 7 days) with its network. The Team page shows a locked account, and its lockouts in the last 24 hours and from how many networks, so a forgotten PIN (one lockout, one network) reads differently from targeted denial.
   - Team Leads can reset their assigned volunteers' PIN; Admins can reset any user's PIN. A reset issues a new one-time PIN, ends every session (`session_version`), clears the lockout and writes a `staff_audit` record.
   - The same people can Unlock an account. Unlock clears the lockout without changing or revealing the PIN, and writes a `staff_audit` record.

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

- **A shared default PIN (`1234`)**: Rejected in #50. Anyone who knew a new Volunteer's Name could claim the account before they did.
- **Per-network throttling only**: Rejected; it would let a patient guesser from many networks keep trying one account. Both budgets apply.
- **A per-network budget for every network, with successes refunded**: Rejected; every desk at the venue shares one address, so 50 attempts with made-up names from any phone on the venue Wi-Fi would shut every desk out, with no recovery.
- **Recovery by reset only**: Rejected; a Volunteer locked out by someone else would have to learn a new PIN mid-shift. Unlock keeps their PIN and is recorded.
- **Desk accounts with roster attribution (ADR 0024)**: Rejected because it prevented team lead delegation, lacked verified per-action accountability, and could not easily support team-level leaderboard aggregations.
- **Email/password per volunteer**: Rejected because 100+ volunteers in field conditions cannot manage passwords and emails without causing desk halts.
