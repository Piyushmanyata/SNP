from datetime import date
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from typing import Annotated, Optional, List, Dict, Any


DateString = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(lambda value: date.fromisoformat(value).isoformat())]


# ---- auth ----
class LoginBody(BaseModel):
    name: str
    pin: str = Field(min_length=4, max_length=4)


class ChangePinBody(BaseModel):
    current_pin: str = Field(min_length=4, max_length=4)
    new_pin: str = Field(min_length=4, max_length=4)


class CreateStaffBody(BaseModel):
    name: str
    role: str  # admin | team_lead | volunteer | clinical_desk_operator
    phone: Optional[str] = None
    team_lead_id: Optional[str] = None
    line: Optional[str] = None  # rx | medicine | specs_fixed | specs_made | ot


class PatchStaffLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: Optional[str] = None


# ---- camps ----
class CampSetupDay(BaseModel):
    day_date: DateString
    seat_limit: int = Field(gt=0)


class CampBody(BaseModel):
    name: str
    venue: str
    camp_date: Optional[DateString] = None
    days: Optional[List[CampSetupDay]] = None
    setup_request_id: Optional[str] = None


class CampDayBody(BaseModel):
    camp_id: str
    day_date: DateString
    seat_limit: int = Field(gt=0)


class DoorManualBody(BaseModel):
    enabled: bool


class PrintWindowBody(BaseModel):
    printing_open: Optional[bool] = None
    mode: Optional[str] = None
    day_id: Optional[str] = None


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
    is_self_registered: bool = False
    manual_entry: bool = False
    manual_exception: bool = False
    manual_reason: Optional[str] = None
    failed_scan_attempts: int = 0
    qr_payload: Optional[str] = None


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


# ---- catalogue ----
class MedicineBody(BaseModel):
    name: str


class FixedPowerBody(BaseModel):
    value: float


class CatalogueActiveBody(BaseModel):
    active: bool


class MedicineOutcome(BaseModel):
    medicine_id: str
    given: bool


# ---- clinical ----
class TranscriptionBody(BaseModel):
    patient_id: str
    diagnosis_options: List[str] = []
    diagnosis_other: Optional[str] = None
    blood_sugar: Optional[str] = None
    bp: Optional[str] = None
    remarks: Optional[str] = None
    prescribed_medicine_ids: List[str] = []
    prescribed_medicines: List[Dict[str, Any]] = []
    specs_measurements: Optional[Dict[str, Any]] = None
    fixed_power_r: Optional[float] = None
    fixed_power_l: Optional[float] = None
    ot_eye: Optional[str] = None
    ot_outcome: Optional[str] = None
    ot_notes: Optional[str] = None
    expected_draft_version: Optional[int] = Field(None, ge=0)
    operation_id: Optional[str] = None


class CompletePrescriptionBody(TranscriptionBody):
    expected_generation: int = 0
    full_transcription_confirmed: bool = False
    none_prescribed: bool = False
    prescribed_lines: List[str] = []
    operation_id: str


class UndoCompletionBody(BaseModel):
    patient_id: str
    expected_generation: int
    reason: str
    operation_id: str


class FulfilmentBody(BaseModel):
    transcription_id: str
    item_type: str  # medicine | specs_fixed | specs_made | ot
    status: str  # fulfilled | not_available | partially_fulfilled | deferred | declined
    collection_date: Optional[str] = None
    collection_venue: Optional[str] = None
    ot_schedule_day_id: Optional[str] = None
    specs_collection_day_id: Optional[str] = None
    medicine_outcomes: List[MedicineOutcome] = []
    issued_power_r: Optional[float] = None
    issued_power_l: Optional[float] = None
    paper_reviewed: bool = False
    reviewed_revision_id: Optional[str] = None
    reviewed_generation: Optional[int] = None
    operation_id: Optional[str] = None


class CorrectionBody(BaseModel):
    transcription_id: Optional[str] = None
    patient_id: Optional[str] = None
    reason: str
    changes: Dict[str, Any] = {}
    expected_generation: int = 0
    operation_id: Optional[str] = None
    full_transcription_confirmed: bool = False
    none_prescribed: bool = False
    prescribed_lines: List[str] = []
    diagnosis_options: List[str] = []
    diagnosis_other: Optional[str] = None
    blood_sugar: Optional[str] = None
    bp: Optional[str] = None
    remarks: Optional[str] = None
    prescribed_medicine_ids: List[str] = []
    prescribed_medicines: List[Dict[str, Any]] = []
    specs_measurements: Optional[Dict[str, Any]] = None
    fixed_power_r: Optional[float] = None
    fixed_power_l: Optional[float] = None
    ot_eye: Optional[str] = None
    ot_outcome: Optional[str] = None
    ot_notes: Optional[str] = None


class IdentityCheckBody(BaseModel):
    patient_id: str
    reason: str
    evidence: Optional[str] = None


class OtScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    venue: str
    venue_sms: Optional[str] = None
    seat_limit: int


class SpecsScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    venue: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
