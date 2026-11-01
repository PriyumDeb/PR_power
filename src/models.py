from enum import Enum
import re
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class TriageLabel(str, Enum):
    CONFIRMED = "confirmed"
    CANNOT_REPRODUCE = "cannot reproduce"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


class TechnicalClaim(BaseModel):
    """Atomic technical claim extracted from an issue or pull request."""
    target_file: Optional[str] = Field(
        default=None,
        description="Path to the file referenced in the claim (e.g. 'src/utils.py')"
    )
    target_symbol: Optional[str] = Field(
        default=None,
        description="Function, class, or method name referenced (e.g. 'calculate_tax')"
    )
    claimed_behavior: str = Field(
        default="Unspecified behavior",
        description="Summary of the claimed bug or expected fix."
    )
    reproduction_snippet: Optional[str] = Field(
        default=None,
        description="Self-contained Python snippet provided or synthesized to reproduce the claim."
    )
    expected_error: Optional[str] = Field(
        default=None,
        description="Name of the exception claimed (e.g. 'ZeroDivisionError', 'TypeError')."
    )
    external_dependencies: List[str] = Field(
        default_factory=list,
        description="External systems or services required (e.g. 'aws', 'database', 'network')."
    )

    @field_validator("target_file", "target_symbol", "expected_error", "reproduction_snippet", mode="before")
    @classmethod
    def clean_null_strings(cls, v: Any) -> Optional[str]:
        """Sanitizes raw string 'null', 'None', or empty values emitted by quantized LLMs."""
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            if cleaned.lower() in {"null", "none", "undefined", "n/a", "nil", ""}:
                return None
            if cleaned.lower().startswith("null (") or cleaned.lower().startswith("none ("):
                m = re.search(r"\b([A-Z][a-zA-Z0-9]*(?:Error|Exception))\b", cleaned)
                if m:
                    return m.group(1)
                return None
            return cleaned
        return str(v)

    @field_validator("external_dependencies", mode="before")
    @classmethod
    def clean_dependencies(cls, v: Any) -> List[str]:
        """Ensures external dependencies cleanly parses even if LLM outputs null or malformed data."""
        if v is None:
            return []
        if isinstance(v, str):
            cleaned = v.strip()
            if cleaned.lower() in {"null", "none", "undefined", "[]", ""}:
                return []
            return [cleaned]
        if isinstance(v, list):
            cleaned_list = []
            for item in v:
                if item is not None:
                    item_str = str(item).strip()
                    if item_str.lower() not in {"null", "none", "undefined", ""}:
                        cleaned_list.append(item_str)
            return cleaned_list
        return []


class VerificationEvidence(BaseModel):
    """Concrete evidence gathered through static AST and dynamic sandboxing."""
    label: TriageLabel
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence score between 0.0 (completely uncertain) and 1.0 (verified proof)."
    )
    summary: str
    target_file: Optional[str] = None
    target_symbol: Optional[str] = None
    symbol_exists: Optional[bool] = None
    file_exists: Optional[bool] = None
    exit_code: Optional[int] = None
    caught_exception: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    reasons_for_uncertainty: List[str] = Field(default_factory=list)
