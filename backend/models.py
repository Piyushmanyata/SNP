from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any


# ---- auth ----
class LoginBody(BaseModel):
    email: EmailStr
    password: str


class CreateStaffBody(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str  # admin | team_lead | volunteer | clinical_desk_operator
    phone: Optional[str] = None
    team_lead_id: Optional[str] = None


# ---- camps ----
class CampBody(BaseModel):
    name: str
    venue: str
    camp_date: str


class CampDayBody(BaseModel):
    camp_id: str
    day_date: str
    seat_limit: int = Field(gt=0)


class PrintWindowBody(BaseModel):
    printing_open: bool


# ---- aadhaar mock ----
class AadhaarDecodeBody(BaseModel):
    payload: str  # simulated QR string


# ---- registration ----
class RegisterBody(BaseModel):
    full_name: str
    age: Optional[int] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    aadhaar_last4: Optional[str] = None
    dob: Optional[str] = None
    aadhaar_scanned: bool = False
    latin_display_name: Optional[str] = None
    camp_day_id: str
    registration_request_id: Optional[str] = None
    override_duplicate: bool = False
    is_self_registered: bool = False
    manual_entry: bool = False
    manual_exception: bool = False
    manual_reason: Optional[str] = None
    failed_scan_attempts: int = 0


class DuplicateCheckBody(BaseModel):
    full_name: str
    age: Optional[int] = None


# ---- desk ----
class QrLookupBody(BaseModel):
    value: str  # patient qr uuid, snp:{uuid}, /p/{uuid}, or reg_no


class ScanBody(BaseModel):
    payload: str  # Aadhaar Secure QR payload


class ScanConfirmBody(BaseModel):
    patient_id: str
    payload: str


# ---- clinical ----
class TranscriptionBody(BaseModel):
    patient_id: str
    diagnosis_options: List[str] = []
    diagnosis_other: Optional[str] = None
    blood_sugar: Optional[str] = None
    bp: Optional[str] = None
    remarks: Optional[str] = None
    specs_measurements: Optional[Dict[str, Any]] = None
    ot_eye: Optional[str] = None
    ot_procedure: Optional[str] = None
    ot_notes: Optional[str] = None


class FulfilmentBody(BaseModel):
    transcription_id: str
    item_type: str  # medicine | specs | ot
    status: str  # fulfilled | not_available | not_required | deferred
    collection_date: Optional[str] = None
    collection_venue: Optional[str] = None
    ot_schedule_day_id: Optional[str] = None
    specs_collection_day_id: Optional[str] = None


class CorrectionBody(BaseModel):
    transcription_id: str
    reason: str
    changes: Dict[str, Any]


class OtScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    venue: str
    seat_limit: int


class SpecsScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    venue: str
    seat_limit: int
