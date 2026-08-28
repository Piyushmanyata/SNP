# Project: SNP Code Quality & Comprehensive Refactoring Sprint

## Architecture
The application stack consists of:
- `frontend/`: React single-page application (React 18 + Tailwind CSS + Lucide + getUserMedia / BarcodeDetector + zxing-wasm)
- `backend/`: FastAPI async Python application with Motor MongoDB driver
- `tests/`: Automated pytest suites (`test_aadhaar_unit.py`, `test_iter3.py`, `backend_test.py`) and Jest frontend test suites

```
                    ┌─────────────────────────┐
                    │      React Frontend     │
                    │  (Desk, Clinical, Admin)│
                    └────────────┬────────────┘
                                 │ REST API (JSON)
                                 ▼
                    ┌─────────────────────────┐
                    │     FastAPI Backend     │
                    │  (Auth, Reg, Clin, Rpt) │
                    └────────────┬────────────┘
                                 │ Async Motor
                                 ▼
                    ┌─────────────────────────┐
                    │     MongoDB Database    │
                    └─────────────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Fix React Hook Dependencies (AadhaarScanner) | Fix 7 hook deps, stale closures on torch & callbacks in `AadhaarScanner.js` | M1 | Survey E1 |
| 2 | Fix React Hook Dependencies (Desk) | Fix 6 hook deps, stale closures in `RegisterModal`, unmemoized `markSeen`/`undoSeen` in `Desk.js` | M1 | Survey E1 |
| 3 | Fix React Hook Dependencies & Board Nesting (AdminDashboard) | Fix 6 hook deps and move nested `Board` component outside render in `AdminDashboard.js` | M1 | Survey E1 |
| 4 | Fix React Hook Dependencies (TemplateEditor) | Memoize `sampleRx` and action handlers in `TemplateEditor.js` | M1 | Survey E1 |
| 5 | Fix Index-as-Key Anti-patterns | Replace index keys with stable identifiers in `AdminDashboard.js` | M1 | Survey E2 |
| 6 | Fix Context & Prop Inline References | Memoize AuthContext provider value and extract static route role constants in `App.js` | M1 | Survey E2 |
| 7 | Decompose AadhaarScanner | Extract `useAadhaarCamera`, `useAadhaarDecode` hooks and 4 presentation subcomponents | M2 | Survey E2 |
| 8 | Decompose Clinical Page | Modularize `Clinical.js` into lookup, summary, prescription, measurements, fulfilment, and modal subcomponents | M2 | Survey E2 |
| 9 | Structured Error Logging | Replace empty catch blocks in `PrintPrescription.js`, `Clinical.js`, and `AadhaarScanner.js` with structured logging | M2 | Survey E2 |
| 10 | Decompose parse_xml_qr & decode_aadhaar | Refactor `backend/aadhaar.py` into single-responsibility helpers (`_parse_xml_attributes`, `_extract_xml_address`, `_normalize_gender`, `_decode_demo_payload`) | M3 | Survey E3 |
| 11 | Decompose _create_registration | Refactor `backend/routes_registration.py` into validation, duplicate check, and doc builder helpers | M3 | Survey E3 |
| 12 | Decompose record_fulfilment | Refactor `backend/routes_clinical.py` into validation matrix, deferral/OT processing, and cleanup helpers | M3 | Survey E3 |
| 13 | Fix Literal `is` Comparisons | Replace all 12 `is True`/`is False` literal comparisons in `backend/tests/backend_test.py` with `==` | M3 | Survey E3 |
| 14 | Clean Backend Inlined Imports & Smells | Promote inlined imports in `routes_auth.py` and `routes_reports.py` to module scope | M3 | Survey E3 |
| 15 | Pytest & Frontend Verification Suite | Verify 100% passing tests across unit and integration test suites, build cleanly | M4 | Survey E3 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Frontend Hooks & Memoization | R1 + AuthContext + App.js + AdminDashboard keys | none | DONE |
| M2 | Frontend Component Decomposition | R2 + AadhaarScanner subcomponents/hooks + Clinical subcomponents + structured errors | M1 | DONE |
| M3 | Backend Python Refactoring & Pytest Cleanliness | R3 + function decomposition + `is` literal replacements + import cleanup | none | DONE |
| M4 | Comprehensive Verification & Gate | R4 + Full test suite pass + Reviewer approvals + Challenger verification + Forensic Audit | M1, M2, M3 | DONE |

## Interface Contracts

### Frontend Subcomponents & Hooks
- `useAadhaarCamera({ readerId, onScanSuccess, onError })` -> `{ cameraState, cameras, currentCameraIndex, torchAvailable, torchOn, startCamera, stopCamera, switchCamera, toggleTorch }`
- `useAadhaarDecode({ onScanned })` -> `{ decoding, error, decode, scanFile, setError }`
- `AadhaarScanner`: Must maintain identical props (`onScanned`, `campId`, `onClose`) and `data-testid` attributes (`scanner-container`, `camera-error`, `toggle-camera`, `toggle-torch`, `scan-file-input`, `manual-input-mode`, `demographic-generate-btn`).
- `Clinical.js`: Must maintain identical API endpoints (`/clinical/lookup`, `/clinical/transcription`, `/clinical/fulfilment`, `/clinical/correct`, `/clinical/history`).

### Backend Helper Interfaces
- `_parse_xml_attributes(raw_xml: str) -> dict`: Extracts XML attributes with entity escaping and regex fallback.
- `_extract_xml_address(attrs: dict) -> str`: Aggregates 10 XML address fields into a normalized address string.
- `_normalize_gender(g: str) -> str`: Returns standard 'M', 'F', or 'O'.
- `_decode_demo_payload(raw: str) -> dict`: Decodes demo pipe-delimited QR strings.
- `_validate_camp_and_day(db, camp_day_id) -> tuple[dict, dict]`: Validates camp and camp day active state.
- `_check_registration_duplicates(db, camp_id, body, person)`: Checks for existing registration or name+last4 collision.
- `_build_patient_document(...) -> dict`: Constructs MongoDB registration document.
- `_validate_fulfilment_matrix(item_type: str, status: str)`: Validates item type and status combination.
- `_process_deferral(db, t, body) -> tuple[dict, dict]`: Handles OT schedule capacity increment and slip generation.
- `_cleanup_prior_fulfilment(db, transcription_id, item_type)`: Releases previously reserved OT seat if applicable.

## Code Layout
- `frontend/src/components/AadhaarScanner.js` & `frontend/src/components/aadhaar/*`
- `frontend/src/pages/Desk.js`
- `frontend/src/pages/Clinical.js` & `frontend/src/pages/clinical/*`
- `frontend/src/pages/AdminDashboard.js`
- `frontend/src/components/TemplateEditor.js`
- `frontend/src/context/AuthContext.js`
- `frontend/src/App.js`
- `frontend/src/constants/roles.js`
- `frontend/src/pages/PrintPrescription.js`
- `backend/aadhaar.py`
- `backend/routes_registration.py`
- `backend/routes_clinical.py`
- `backend/routes_auth.py`
- `backend/routes_reports.py`
- `backend/tests/backend_test.py`
- `backend/tests/test_aadhaar_unit.py`
- `backend/tests/test_iter3.py`
