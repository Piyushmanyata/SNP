# Original User Request

## 2026-08-27T13:24:12Z

Fix Aadhaar camera scanning to make it fast and reliable during desk registration. Open a PR, monitor CI and resolve any failures until green, then merge to main, push upstream, and purge the working branch.

Working directory: c:/Users/piyus/OneDrive/Documents/SNP
Integrity mode: development

## Requirements

### R1. Aadhaar Camera Scanning Reliability & Speed
Ensure camera-based Aadhaar QR code and text detection reliably detects and decodes Aadhaar cards quickly across varied lighting and video feed conditions without hanging or failing to initialize.

### R2. Test Suite & Verification Compliance
Maintain full test suite integrity: all unit tests, typechecks, linter checks, and database tests must pass cleanly with zero regressions.

### R3. Git & CI Automation Lifecycle
Execute the complete delivery lifecycle:
1. Create a dedicated feature branch for the changes.
2. Commit changes and push branch to origin.
3. Open a Pull Request on GitHub.
4. Monitor CI workflow run(s), diagnose and fix any test/build failures until all checks pass green.
5. Merge the PR into the target default branch (main / master).
6. Push updated default branch to remote and purge/delete the feature branch locally and remotely.

## Acceptance Criteria

### Camera Scanning Functionality
- [ ] Camera stream starts cleanly and Aadhaar QR codes / text scans trigger decoding promptly.
- [ ] Decode pipeline handles valid Aadhaar QR and text extracts accurately without unhandled errors.

### Quality & Regression Verification
- [ ] Local verification commands (
pm test, 
pm run typecheck, 
pm run lint, and 
pm run build or repo equivalents) pass with 0 errors.
- [ ] Existing Aadhaar component and utility tests remain green.

### PR, CI & Git Lifecycle
- [ ] Pull Request is successfully created for the feature branch.
- [ ] GitHub Actions / CI status checks run and pass completely green.
- [ ] Pull Request is merged into the default branch.
- [ ] Upstream repository is synced with the merge commit.
- [ ] Temporary feature branch is purged both locally and on the remote.
