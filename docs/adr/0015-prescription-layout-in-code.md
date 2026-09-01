# ADR 0015: Prescription layout in code, sponsor logos as data

## Context

The prescription is a fixed printed form the trust has used for years; the reference artwork is in the repo. The template system nevertheless allowed an admin to edit the header title, the subtitle, the footer, and the visibility and height of seven layout blocks, behind a draft, publish, and restore-defaults workflow with versioning.

None of that is wanted. The only thing that genuinely changes between camps is which sponsor's logo appears. The people using this are not technical, and every editable field is a way for the printed prescription to come out wrong on a camp morning.

## Decision

- Header title, subtitle, footer, and the block layout become constants in the print component, reproducing the reference artwork.
- The only stored template data is the sponsor logo list.
- Draft, publish, restore-defaults, and template versioning are deleted. A logo change takes effect immediately.
- The admin screen is a single Sponsor logos panel: upload, reorder, delete. Existing size and MIME validation is kept.

## Consequences

The prescription cannot be broken from the UI or from the API. Roughly a hundred and fifty lines of backend and most of the template editor are deleted. Changing the printed form is now a code change and a deploy, which is correct for a form that changes once every few years and wrong for one that changes per camp — the trust has confirmed it is the former.

## Rejected alternatives

- Keep the schema and hide the UI — ships fastest and migrates nothing, but leaves dead fields and live endpoints that can still rewrite the prescription, and invites someone to re-expose them.
- Keep draft and publish for logos — guards against a wrong logo going live mid-camp, at the cost of a two-step flow for a single image upload and retaining the versioning machinery this ADR exists to remove.
