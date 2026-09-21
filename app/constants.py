"""Domain enums and shared constants (synthetic / educational use only)."""

from enum import Enum


class UserRole(str, Enum):
    GENERAL_ADMIN = "general_admin"
    CENTER_ADMIN = "center_admin"
    SURGEON = "surgeon"
    SUPERVISOR = "supervisor"
    COORDINATOR = "coordinator"
    # Legacy alias kept for older DBs / tests during migration window
    ADMIN = "general_admin"


class EyeSide(str, Enum):
    OD = "OD"  # right
    OS = "OS"  # left


class ComplicationType(str, Enum):
    PCR = "pcr"
    ZONULODIALYSIS = "zonulodialysis"
    IRIS_RUPTURE = "iris_rupture"
    DESCEMET_DETACHMENT = "descemet_detachment"
    BLEEDING = "bleeding"
    OTHER = "other"


class SurgicalStage(str, Enum):
    """Stage at which the complication occurred."""

    CAPSULORHEXIS = "capsulorhexis"
    HYDRODISSECTION = "hydrodissection"
    NUCLEUS_EMULSIFICATION = "nucleus_emulsification"
    CORTEX_REMOVAL = "cortex_removal"
    IOL_INSERTION = "iol_insertion"
    OTHER = "other"


class IOLPosition(str, Enum):
    BAG = "bag"
    SULCUS = "sulcus"
    ACIOL = "aciol"
    SCLERAL_FIXATED = "scleral_fixated"
    LEFT_APHAKIC = "left_aphakic"
    OTHER = "other"


class VisitType(str, Enum):
    DAY_1 = "day_1"
    WEEK_1 = "week_1"
    MONTH_1 = "month_1"
    MONTH_3 = "month_3"
    MONTH_6 = "month_6"
    YEAR_1 = "year_1"
    UNSCHEDULED = "unscheduled"
    OTHER = "other"


VISIT_TYPE_LABELS: dict[str, str] = {
    VisitType.DAY_1.value: "Día 1",
    VisitType.WEEK_1.value: "Semana 1",
    VisitType.MONTH_1.value: "Mes 1",
    VisitType.MONTH_3.value: "Mes 3",
    VisitType.MONTH_6.value: "Mes 6",
    VisitType.YEAR_1.value: "Año 1",
    VisitType.UNSCHEDULED.value: "No programada",
    VisitType.OTHER.value: "Otra",
}


IOL_TYPE_OPTIONS: dict[str, str] = {
    "monofocal": "Monofocal",
    "toric": "Tórica",
    "edof": "EDOF",
    "multifocal": "Multifocal",
    "panoptix": "PanOptix",
    "other": "Otra",
}


DEFAULT_INSTITUTION_CODE = "CODET"
CENTER_CODE_UANL = "HU_UANL"

TRAINING_LEVEL_OPTIONS: dict[str, str] = {
    "r1": "R1",
    "r2": "R2",
    "r3": "R3",
    "r4_plus": "R4 o superior",
    "fellow": "Fellow",
    "adscrito": "Adscrito",
    "na": "No aplica",
}

ACCOUNT_STATUS = {
    "pending": "Pendiente",
    "active": "Activa",
    "rejected": "Rechazada",
    "suspended": "Suspendida",
}


RISK_FACTOR_CATALOG: dict[str, str] = {
    "small_pupil": "Pupila pequeña",
    "white_cataract": "Catarata blanca",
    "dense_cataract": "Catarata densa / núcleo duro",
    "pseudoexfoliation": "Pseudoexfoliación",
    "weak_zonules": "Zonulopatía / zónulas débiles",
    "subluxation": "Subluxación",
    "ifis": "IFIS",
    "trauma_history": "Trauma",
    "previous_vitrectomy": "Vitrectomía previa",
    "shallow_ac": "Cámara anterior estrecha",
    "poor_visualization": "Mala visualización",
    "combined_surgery": "Cirugía combinada",
    "posterior_polar": "Catarata polar posterior",
    "high_myopia": "Miopía alta",
    "other": "Otro",
}

# Clinically motivated interaction pairs for Surgical Risk Profile MVP
RISK_INTERACTION_PAIRS: tuple[tuple[str, str], ...] = (
    ("small_pupil", "dense_cataract"),
    ("pseudoexfoliation", "weak_zonules"),
    ("white_cataract", "poor_visualization"),
    ("previous_vitrectomy", "subluxation"),
)

# Configurable sufficiency thresholds (Surgical Risk Profile)
RISK_MIN_CASES = 20
RISK_MIN_EVENTS = 5
RISK_MIN_COMBO_CASES = 8
RISK_CATEGORY_THRESHOLDS = (0.03, 0.06)  # <3% bajo, <6% intermedio, else elevado


COMPLICATION_TYPE_LABELS: dict[str, str] = {
    ComplicationType.PCR.value: "RCP (ruptura de cápsula posterior)",
    ComplicationType.ZONULODIALYSIS.value: "Zonulodiálisis",
    ComplicationType.IRIS_RUPTURE.value: "Ruptura de iris",
    ComplicationType.DESCEMET_DETACHMENT.value: "Desprendimiento de Descemet",
    ComplicationType.BLEEDING.value: "Sangrado",
    ComplicationType.OTHER.value: "Otro",
}


SURGICAL_STAGE_LABELS: dict[str, str] = {
    SurgicalStage.CAPSULORHEXIS.value: "Capsulorrexis",
    SurgicalStage.HYDRODISSECTION.value: "Hidrodisección",
    SurgicalStage.NUCLEUS_EMULSIFICATION.value: "Emulsificación del núcleo",
    SurgicalStage.CORTEX_REMOVAL.value: "Aspiración de corteza",
    SurgicalStage.IOL_INSERTION.value: "Inserción del LIO",
    SurgicalStage.OTHER.value: "Otra",
}


IOL_POSITION_LABELS: dict[str, str] = {
    IOLPosition.BAG.value: "Saco capsular",
    IOLPosition.SULCUS.value: "Surco",
    IOLPosition.ACIOL.value: "LIO de cámara anterior",
    IOLPosition.SCLERAL_FIXATED.value: "Fijación escleral",
    IOLPosition.LEFT_APHAKIC.value: "Afáquico",
    IOLPosition.OTHER.value: "Otra",
}


ROLE_LABELS: dict[str, str] = {
    UserRole.GENERAL_ADMIN.value: "Administrador general",
    UserRole.CENTER_ADMIN.value: "Administrador de centro",
    UserRole.SURGEON.value: "Cirujano",
    UserRole.SUPERVISOR.value: "Supervisor",
    UserRole.COORDINATOR.value: "Coordinador",
}

# Roles a center_admin may assign (never center_admin / general_admin)
ASSIGNABLE_CENTER_ROLES: tuple[str, ...] = (
    UserRole.SURGEON.value,
    UserRole.SUPERVISOR.value,
    UserRole.COORDINATOR.value,
)


class ReinterventionRequired(str, Enum):
    YES = "yes"
    NO = "no"
    PENDING = "pending"


class ReinterventionStatus(str, Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RetinaRelated(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class ReinterventionType(str, Enum):
    ANTERIOR_VITRECTOMY = "anterior_vitrectomy"
    POSTERIOR_VITRECTOMY = "posterior_vitrectomy"
    IOL_REPOSITION = "iol_reposition"
    SCLERAL_FIXATED_LENS = "scleral_fixated_lens"
    WOUND_REPAIR = "wound_repair"
    AC_WASH = "ac_wash"
    OTHER = "other"
    UNSPECIFIED = "unspecified"


REINTERVENTION_REQUIRED_LABELS: dict[str, str] = {
    ReinterventionRequired.YES.value: "Sí",
    ReinterventionRequired.NO.value: "No necesaria",
    ReinterventionRequired.PENDING.value: "Pendiente",
}

REINTERVENTION_STATUS_LABELS: dict[str, str] = {
    ReinterventionStatus.PENDING.value: "Pendiente",
    ReinterventionStatus.SCHEDULED.value: "Programada",
    ReinterventionStatus.COMPLETED.value: "Completada",
    ReinterventionStatus.CANCELLED.value: "Cancelada",
}

RETINA_RELATED_LABELS: dict[str, str] = {
    RetinaRelated.YES.value: "Sí",
    RetinaRelated.NO.value: "No",
    RetinaRelated.UNKNOWN.value: "Desconocido",
}

REINTERVENTION_TYPE_LABELS: dict[str, str] = {
    ReinterventionType.ANTERIOR_VITRECTOMY.value: "Vitrectomía anterior",
    ReinterventionType.POSTERIOR_VITRECTOMY.value: "Vitrectomía posterior / retina",
    ReinterventionType.IOL_REPOSITION.value: "Recolocación o intercambio de LIO",
    ReinterventionType.SCLERAL_FIXATED_LENS.value: "Lente fijado a esclera",
    ReinterventionType.WOUND_REPAIR.value: "Reparación de herida",
    ReinterventionType.AC_WASH.value: "Lavado de cámara anterior",
    ReinterventionType.OTHER.value: "Otra",
    ReinterventionType.UNSPECIFIED.value: "No especificada",
}
