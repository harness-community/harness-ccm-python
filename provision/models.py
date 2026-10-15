from dataclasses import dataclass, field


@dataclass
class FolderAction:
    name: str
    operation: str  # create | reuse
    existing_uuid: str | None = None


@dataclass
class PerspectiveAction:
    name: str
    folder_name: str
    bucket: str
    conditions: list
    operation: str  # create | update | skip
    existing_uuid: str | None = None
    existing_folder_id: str | None = None


@dataclass
class BudgetAction:
    key: str
    name: str
    perspective_name: str
    bucket: str
    folder: str
    budget: dict
    operation: str  # create | update | skip
    existing_uuid: str | None = None
    existing_amount: float = 0


@dataclass
class GroupAction:
    name: str
    bucket: str
    folder: str
    budget_keys: list
    period: str
    start_time: int
    monthly_breakdown: bool
    monthly_amounts: list
    amount: float
    operation: str  # create | update | skip
    existing_uuid: str | None = None


@dataclass
class PlanIssue:
    kind: str
    name: str
    error: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "name": self.name, "error": self.error}


def public_issues(items: list) -> list:
    published = []
    for item in items:
        if isinstance(item, PlanIssue):
            published.append(item.as_dict())
        else:
            published.append(item)
    return published


@dataclass
class ExecutionResult:
    name: str
    uuid: str | None = None
    created: bool = False
    kind: str = ""
    amount: float = 0
    bucket: str | None = None
    period: str | None = None
    start_time: int | None = None
    monthly_breakdown: bool = False
    monthly_amounts: list = field(default_factory=list)
    folder: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "uuid": self.uuid,
            "created": self.created,
            "kind": self.kind,
            "amount": self.amount,
            "bucket": self.bucket,
            "period": self.period,
            "start_time": self.start_time,
            "monthly_breakdown": self.monthly_breakdown,
            "monthly_amounts": list(self.monthly_amounts),
            "folder": self.folder,
        }


@dataclass
class ProvisionPlan:
    folders: list = field(default_factory=list)
    perspectives: list = field(default_factory=list)
    budgets: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    account_count: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors
