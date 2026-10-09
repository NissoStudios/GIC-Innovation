"""Validation helpers used by services and tests."""

from __future__ import annotations

from datetime import date
from pathlib import Path


class ValidationError(ValueError):
    """Raised when user-provided domain data is invalid."""


def required_text(value: object, label: str, *, max_length: int = 200) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"Le champ « {label} » est obligatoire.")
    if len(text) > max_length:
        raise ValidationError(
            f"Le champ « {label} » ne doit pas dépasser {max_length} caractères."
        )
    return text


def optional_text(value: object, *, max_length: int = 2_000) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValidationError(f"Le texte ne doit pas dépasser {max_length} caractères.")
    return text


def positive_float(value: object, label: str) -> float:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"« {label} » doit être un nombre.") from exc
    if number <= 0:
        raise ValidationError(f"« {label} » doit être supérieur à zéro.")
    return number


def non_negative_float(value: object, label: str) -> float:
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"« {label} » doit être un nombre.") from exc
    if number < 0:
        raise ValidationError(f"« {label} » ne peut pas être négatif.")
    return number


def non_negative_int(value: object, label: str) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"« {label} » doit être un nombre entier.") from exc
    if number < 0:
        raise ValidationError(f"« {label} » ne peut pas être négatif.")
    return number


def iso_date(value: object, label: str, *, required: bool = True) -> str | None:
    text = str(value or "").strip()
    if not text and not required:
        return None
    if not text:
        raise ValidationError(f"Le champ « {label} » est obligatoire.")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValidationError(
            f"« {label} » doit respecter le format AAAA-MM-JJ."
        ) from exc


def existing_optional_file(value: object, label: str = "Fichier") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    path = Path(text)
    if not path.is_file():
        raise ValidationError(f"Le fichier indiqué pour « {label} » est introuvable.")
    return str(path.resolve())

