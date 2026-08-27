# SNP Camps — Medical Camp Management System

Free eye camp management desk and clinical workflow system, built on the **Emergent** stack (React + FastAPI + MongoDB).

---

## Architecture Overview

```
SNP/
├── backend/                  # FastAPI async Python backend
│   ├── server.py             # FastAPI entrypoint & router registry
│   ├── db.py                 # Async Motor MongoDB connection pool
│   ├── models.py             # Pydantic schemas & validation
│   ├── security.py           # JWT token generation & password hashing (bcrypt)
│   ├── helpers.py            # Aadhaar HMAC duplicate keys & helpers
│   ├── aadhaar.py            # Aadhaar parser & mock decoder
│   ├── serializers.py        # MongoDB document JSON serializers
│   ├── routes_*.py           # Modular route handlers (auth, camps, desk, clinical, etc.)
│   ├── tests/                # Pytest regression suite
│   └── requirements.txt      # Python dependencies
├── frontend/                 # React single-page application
│   ├── public/               # Static HTML shell
│   ├── src/
│   │   ├── App.js            # App router & role-based guards
│   │   ├── pages/            # Role pages (Desk, Clinical, Admin, Login, SelfRegister)
│   │   ├── components/       # UI components (AadhaarScanner, Layout, TemplateEditor)
│   │   ├── context/          # AuthContext & session state
│   │   └── lib/              # Axios API client & utilities
│   ├── tailwind.config.js    # Tailwind styling config
│   └── package.json          # React dependencies and scripts
├── .emergent/                # Emergent runtime & cron configurations
└── memory/                   # PRD specifications and test credentials
```

---

## Key Roles & Operational Flow

| Role | Permissions & Responsibilities |
|---|---|
| **Admin** | Full system access: Camps, Camp Days, Staff accounts, OT Schedules, Clinical Templates, Audit Logs, and CSV Exports. |
| **Team Lead** | Camp desk supervision; create and manage Volunteer accounts on their assigned team. |
| **Volunteer** | Desk operations: register patients (Aadhaar scan or manual), print prescription form, mark patient as seen. |
| **Clinical Desk Operator** | Clinical workflow: eligibility verification, prescription transcription, medication/spectacle fulfilment, OT scheduling, deferral slips. |
| **Patient** | Public self-registration (`/self-register`) producing a patient QR code scanned by desk staff. |

---

## Camp Lifecycle

1. **Registration**: Volunteer scans patient's Aadhaar card or enters details. A `Person` duplicate key (HMAC SHA-256) checks for duplicate registrations across the active camp.
2. **Presence & Print**: Volunteer clicks **Print Prescription** (A4 form with patient demographic QR and blank clinical examination area). This records `printed_at` presence.
3. **Doctor Consultation**: Doctor examines patient and writes clinical notes on physical paper prescription form.
4. **Mark Seen**: Volunteer marks patient as `seen` once examination begins.
5. **Clinical Fulfilment**: Clinical operator transcribes prescriptions, fulfills medicines/spectacles, or schedules OT surgery.

---

## Environment Variables

Copy `.env.example` to `.env` or set environment variables:

```bash
# Backend
MONGO_URL=mongodb://localhost:27017
DB_NAME=snp_camps
AADHAAR_HASH_PEPPER=your_secure_random_pepper
JWT_SECRET=your_secure_jwt_secret
ADMIN_EMAIL=admin@snpcamps.org
ADMIN_PASSWORD=AdminCamp@2026
CORS_ORIGINS=*

# Frontend
REACT_APP_BACKEND_URL=http://localhost:8000
```

---

## Local Development

### 1. Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Backend API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/health`

### 2. Frontend (React)

```bash
cd frontend
npm install
npm start
```

Runs the application at `http://localhost:3000`.

---

## Testing & Verification

### Frontend Verification

```bash
cd frontend
npm test
npm run build
```

### Backend Verification

```bash
cd backend
pytest tests/
```

---

## Deployment

The application is configured for deployment on the Emergent platform using `.emergent/` runtime manifests and cron jobs.
