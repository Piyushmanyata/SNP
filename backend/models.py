from datetime import date
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Literal, Optional, List, Dict, Any

from sms import clean_sms_venue, sms_venue_problem

NAME_LIMIT = 100
ADDRESS_LIMIT = 300


DateString = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$"), AfterValidator(lambda value: date.fromisoformat(value).isoformat())]
QrPayload = Annotated[str, Field(max_length=16000)]
RequestId = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")]


def _checked_sms_venue(venue: str, venue_sms: Optional[str]) -> Optional[str]:
    short = clean_sms_venue(venue_sms) or None
    if not short and not venue.strip():
        return None
    problem = sms_venue_problem(short or clean_sms_venue(venue))
    if problem:
        raise ValueError(problem if short else f"{problem}; set a short SMS venue")
    return short


# ---- auth ----
class LoginBody(BaseModel):
    name: str
    pin: str = Field(min_length=4, max_length=6)


class ChangePinBody(BaseModel):
    current_pin: str = Field(min_length=4, max_length=6)
    new_pin: str = Field(min_length=4, max_length=6)


class CreateStaffBody(BaseModel):
    name: str = Field(max_length=80)
    role: str  # admin | team_lead | volunteer | clinical_desk_operator
    phone: Optional[str] = None
    team_lead_id: Optional[str] = None
    line: Optional[str] = None  # rx | medicine | specs_fixed | specs_made | ot


class PatchStaffLineBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line: Optional[str] = None


class PatchStaffTeamLeadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    team_lead_id: Optional[str] = None


# ---- camps ----
class CampSetupDay(BaseModel):
    day_date: DateString
    seat_limit: int = Field(gt=0)


class CampBody(BaseModel):
    name: str = Field(max_length=80)
    venue: str
    venue_sms: Optional[str] = None
    camp_date: Optional[DateString] = None
    camp_number: Optional[int] = Field(default=None, gt=0)
    days: Optional[List[CampSetupDay]] = None
    setup_request_id: Optional[str] = None

    @model_validator(mode="after")
    def check_sms_venue(self) -> "CampBody":
        self.venue_sms = _checked_sms_venue(self.venue, self.venue_sms)
        return self


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
    payload: QrPayload


# ---- registration ----
class RegisterBody(BaseModel):
    full_name: str = Field(max_length=NAME_LIMIT)
    age: Optional[int] = None
    phone: Optional[str] = Field(default=None, max_length=20)
    gender: Optional[Literal["M", "F", "O"]] = None
    address: Optional[str] = Field(default=None, max_length=ADDRESS_LIMIT)
    aadhaar_last4: Optional[str] = Field(default=None, pattern=r"^\d{4}$")
    dob: Optional[str] = None
    aadhaar_scanned: bool = False
    latin_display_name: Optional[str] = Field(default=None, max_length=NAME_LIMIT)
    camp_day_id: str = Field(max_length=24)
    registration_request_id: Optional[RequestId] = None
    is_self_registered: bool = False
    manual_reason: Optional[str] = Field(default=None, max_length=200)
    at_door: bool = False
    qr_payload: Optional[QrPayload] = None
    review_confirmed_id: Optional[str] = Field(default=None, max_length=24)


class DuplicateCheckBody(BaseModel):
    full_name: str
    age: Optional[int] = None


# ---- desk ----
class QrLookupBody(BaseModel):
    value: str  # patient qr uuid, snp:{uuid}, /p/{uuid}, or reg_no


class ScanBody(BaseModel):
    payload: QrPayload


class ScanConfirmBody(BaseModel):
    patient_id: str
    payload: QrPayload


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
    status: str  # fulfilled | not_available | partially_fulfilled | deferred | declined | cancelled
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
    reason: str = Field(max_length=300)
    evidence: Optional[str] = Field(default=None, max_length=300)


class OtScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    venue: str
    venue_sms: Optional[str] = None
    seat_limit: int

    @model_validator(mode="after")
    def check_sms_venue(self) -> "OtScheduleBody":
        self.venue_sms = _checked_sms_venue(self.venue, self.venue_sms)
        return self


class SpecsScheduleBody(BaseModel):
    camp_id: str
    day_date: str
    end_date: Optional[str] = None
    venue: str
    venue_sms: Optional[str] = None

    @model_validator(mode="after")
    def check_sms_venue(self) -> "SpecsScheduleBody":
        self.venue_sms = _checked_sms_venue(self.venue, self.venue_sms)
        return self
