# ADR 0085: Specs SMS are Service Implicit and do not state hours

**Amends ADR 0076.**

## Context

- ADR 0076 put the fixed 10:00 AM–5:00 PM collection hours into the Specs Token and Specs Reminder SMS as static text.
- STPL DLT approved those two templates only as Promotional. A Promotional SMS fails for every number on DND with "DND: Failed due to Preference Category on DLT", so a large share of patients never received their spectacles token.
- Reworded "SNP Specs Token SI" and "SNP Specs Reminder SI" were approved as Service Implicit on 26 September 2026 (DLT IDs `1777179043925249659` and `1777179043934974720`, header SZWTRT). The approved text drops the hours and keeps the five variables in the same order: camp_no, date, end_date, venue, reg_no.

## Decision

- `SPECS_TOKEN` and `SPECS_REMINDER` match the approved SI text exactly. They say "{date} से {end_date} के बीच {venue} पर" and no longer state hours.
- MSG91 keeps its template IDs. Each SI text is a new version (v1.1) of the existing `SNP_Specs_Token` and `SNP_Specs_Reminder` templates, so `MSG91_TEMPLATE_SPECS_TOKEN` and `MSG91_TEMPLATE_SPECS` do not change.
- Collection hours stay fixed at 10:00–17:00 (ADR 0076). Screens and the printed token still show them. `SPECS_CHANGE` keeps its hours; it is a separate template.

## Consequences

- DND patients receive the spectacles token and reminder.
- The SMS no longer tells the patient the hours; the printed token does.
- MSG91 verified both v1.1 versions, and they were marked active on 27 September 2026.

## Rejected alternatives

- **Keep the Promotional templates with hours.** The wording is richer, but DND numbers never receive it.
- **Create new MSG91 templates.** Works, but changes two flow IDs in the production env file for no benefit.
