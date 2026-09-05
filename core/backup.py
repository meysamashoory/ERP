"""Sectional backup and restore for the on-premise ERP.

Archives are zip files with a manifest plus one JSON dump per section.
The destination / source is a filesystem path on the server (folder or .zip).
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import IntegrityError, models, transaction
from django.utils import timezone

FORMAT = "erp-backup-v1"

# Parent-first so dumps stay readable; wipe uses reverse order + Collector.
_SECTION_SPECS: dict[str, dict] = {
    "users": {
        "label": "کاربران و دسترسی‌ها",
        "hint": "حساب‌های ورود، نقش‌ها و اجازه ویرایش داده دیگران",
        "models": [("auth", "User"), ("accounts", "UserProfile")],
        "replace": False,
    },
    "catalog": {
        "label": "داده‌های پایه سامانه",
        "hint": "واحدها، دستگاه‌ها، محصولات، قالب‌ها و فهرست دلایل",
        "models": [
            ("catalog", "ProductionUnit"),
            ("catalog", "Machine"),
            ("catalog", "ProductGroup"),
            ("catalog", "ProductSubGroup"),
            ("catalog", "Product"),
            ("catalog", "ProductionTypeOption"),
            ("catalog", "StoppageReason"),
            ("catalog", "DeviationReason"),
            ("catalog", "ProgramChangeReason"),
            ("catalog", "MoldOption"),
        ],
        "replace": True,
    },
    "planning": {
        "label": "برنامه‌ریزی هفتگی",
        "hint": "برنامه‌های هفتگی، ردیف‌ها و خطوط تولید برنامه‌ریزی‌شده",
        "models": [
            ("planning", "WeeklyPlan"),
            ("planning", "WeeklyPlanItem"),
            ("planning", "WeeklyPlanLine"),
        ],
        "replace": True,
    },
    "production": {
        "label": "ثبت و سوابق تولید",
        "hint": "ثبت روزانه اتصالات و لوله، برنامه‌های تولید و توقفات",
        "models": [
            ("production", "FittingProduction"),
            ("production", "PipeProduction"),
            ("production", "ProductionProgram"),
            ("production", "ProductionDayEntry"),
            ("production", "ProductionStoppage"),
        ],
        "replace": True,
    },
}


def default_backup_dir() -> Path:
    configured = getattr(settings, "BACKUP_DEFAULT_DIR", None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "backups"


def available_sections() -> list[dict]:
    rows = []
    for key, spec in _SECTION_SPECS.items():
        rows.append(
            {
                "key": key,
                "label": spec["label"],
                "hint": spec["hint"],
                "replace": spec["replace"],
            }
        )
    return rows


def all_section_keys() -> list[str]:
    return list(_SECTION_SPECS.keys())


def normalize_sections(keys: Iterable[str] | None) -> list[str]:
    chosen: list[str] = []
    raw = [str(k).strip() for k in (keys or []) if str(k).strip()]
    if not raw or "full" in raw or "all" in raw:
        return all_section_keys()
    for key in all_section_keys():
        if key in raw:
            chosen.append(key)
    if not chosen:
        raise ValueError("دست‌کم یک بخش را برای پشتیبان انتخاب کنید.")
    unknown = [k for k in raw if k not in _SECTION_SPECS and k not in {"full", "all"}]
    if unknown:
        raise ValueError("بخش نامعتبر: " + "، ".join(unknown))
    return chosen


def resolve_user_path(raw: str) -> Path:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("آدرس را وارد کنید.")
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = (Path(settings.BASE_DIR) / path)
    try:
        if path.exists():
            path = path.resolve()
        else:
            parent = path.parent
            if parent.exists():
                path = parent.resolve() / path.name
            else:
                path = path if path.is_absolute() else path.resolve()
    except OSError as exc:
        raise ValueError(f"آدرس نامعتبر است: {exc}") from exc
    return path


def resolve_backup_dest(raw: str) -> Path:
    path = resolve_user_path(raw)
    db_name = settings.DATABASES.get("default", {}).get("NAME")
    if db_name:
        db_path = Path(db_name)
        if not db_path.is_absolute():
            db_path = Path(settings.BASE_DIR) / db_path
        try:
            if path.exists() and path.resolve() == db_path.resolve():
                raise ValueError("نمی‌توان پرونده پایگاه‌داده را به‌عنوان مقصد پشتیبان استفاده کرد.")
        except OSError:
            pass
    if path.suffix.lower() == ".zip":
        return path
    if path.exists() and path.is_file():
        raise ValueError("آدرس مقصد باید پوشه یا پرونده با پسوند zip باشد.")
    stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    return path / f"erp-backup-{stamp}.zip"


def resolve_restore_source(raw: str) -> Path:
    path = resolve_user_path(raw)
    if not path.exists():
        raise ValueError("آدرس پشتیبان پیدا نشد.")
    if path.is_dir():
        if not (path / "manifest.json").is_file():
            raise ValueError("در این پوشه پرونده manifest.json نیست.")
        return path
    if path.suffix.lower() != ".zip":
        raise ValueError("پرونده پشتیبان باید zip باشد یا پوشه استخراج‌شده با manifest.")
    return path


def _model(app_label: str, name: str):
    return apps.get_model(app_label, name)


def _section_models(key: str) -> list[type[models.Model]]:
    spec = _SECTION_SPECS[key]
    found: list[type[models.Model]] = []
    for app_label, name in spec["models"]:
        try:
            model = _model(app_label, name)
        except LookupError:
            continue
        if model._meta.abstract:
            continue
        found.append(model)
    return found


def _serialize_section(key: str) -> str:
    objects: list[models.Model] = []
    for model in _section_models(key):
        objects.extend(list(model.objects.all().order_by("pk")))
    return serializers.serialize("json", objects, ensure_ascii=False, indent=2)


def _media_names(models_list: list[type[models.Model]]) -> list[str]:
    names: list[str] = []
    for model in models_list:
        for field in model._meta.fields:
            if not isinstance(field, models.FileField):
                continue
            for obj in model.objects.exclude(**{f"{field.name}": ""}).iterator():
                fh = getattr(obj, field.name, None)
                if fh and getattr(fh, "name", ""):
                    names.append(fh.name)
    return names


def _write_media(zf: zipfile.ZipFile, rel_names: Iterable[str]) -> int:
    root = Path(settings.MEDIA_ROOT)
    written = 0
    seen: set[str] = set()
    for rel in rel_names:
        rel = str(rel).replace("\\", "/").lstrip("/")
        if not rel or rel in seen:
            continue
        seen.add(rel)
        src = root / rel
        if src.is_file():
            zf.write(src, f"media/{rel}")
            written += 1
    return written


@dataclass
class BackupResult:
    path: str
    sections: list[str]
    size: int
    media_files: int


def create_backup(*, sections: Iterable[str], dest: str, created_by: str = "") -> BackupResult:
    keys = normalize_sections(sections)
    dest_file = resolve_backup_dest(dest)
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "format": FORMAT,
        "created_at": timezone.now().isoformat(),
        "created_by": created_by or "",
        "sections": keys,
        "label": "پشتیبان سامانه برنامه‌ریزی و کنترل تولید",
    }
    media_count = 0
    with zipfile.ZipFile(dest_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for key in keys:
            zf.writestr(f"data/{key}.json", _serialize_section(key))
            media_count += _write_media(zf, _media_names(_section_models(key)))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return BackupResult(
        path=str(dest_file),
        sections=keys,
        size=dest_file.stat().st_size,
        media_files=media_count,
    )


class _Archive:
    def read(self, name: str) -> bytes:
        raise NotImplementedError

    def namelist(self) -> list[str]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class _ZipArchive(_Archive):
    def __init__(self, path: Path):
        self._zf = zipfile.ZipFile(path, "r")

    def read(self, name: str) -> bytes:
        return self._zf.read(name)

    def namelist(self) -> list[str]:
        return self._zf.namelist()

    def close(self) -> None:
        self._zf.close()


class _DirArchive(_Archive):
    def __init__(self, path: Path):
        self.root = path

    def read(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def namelist(self) -> list[str]:
        names: list[str] = []
        for item in self.root.rglob("*"):
            if item.is_file():
                names.append(str(item.relative_to(self.root)).replace("\\", "/"))
        return names


def open_archive(path: Path) -> _Archive:
    if path.is_dir():
        return _DirArchive(path)
    if not zipfile.is_zipfile(path):
        raise ValueError("پرونده پشتیبان zip معتبر نیست.")
    return _ZipArchive(path)


def read_manifest(source: str | Path) -> dict:
    path = resolve_restore_source(str(source))
    archive = open_archive(path)
    try:
        raw = archive.read("manifest.json")
    except (KeyError, FileNotFoundError) as exc:
        archive.close()
        raise ValueError("این آدرس پشتیبان سامانه نیست (manifest نیست).") from exc
    archive.close()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("manifest پشتیبان خراب است.") from exc
    if data.get("format") != FORMAT:
        raise ValueError("نسخه پشتیبان پشتیبانی نمی‌شود.")
    sections = [k for k in data.get("sections") or [] if k in _SECTION_SPECS]
    data["sections"] = sections
    return data


def _wipe_section(key: str) -> int:
    models_list = list(reversed(_section_models(key)))
    deleted = 0
    for model in models_list:
        deleted += model.objects.all().delete()[0]
    return deleted


def _extract_media(archive: _Archive) -> int:
    root = Path(settings.MEDIA_ROOT)
    count = 0
    for name in archive.namelist():
        rel = str(name).replace("\\", "/")
        if not rel.startswith("media/") or rel.endswith("/"):
            continue
        inner = rel[len("media/") :]
        if not inner or ".." in Path(inner).parts:
            continue
        dest = root / inner
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.read(name))
        count += 1
    return count


@dataclass
class RestoreResult:
    source: str
    sections: list[str]
    loaded: int
    deleted: int
    media_files: int


def restore_backup(*, source: str, sections: Iterable[str] | None = None) -> RestoreResult:
    path = resolve_restore_source(source)
    info = read_manifest(path)
    available = info.get("sections") or []
    requested = normalize_sections(sections) if sections else list(available)
    chosen = [k for k in requested if k in available]
    if not chosen:
        raise ValueError("هیچ‌یک از بخش‌های انتخاب‌شده در این پشتیبان نیست.")

    archive = open_archive(path)
    loaded = 0
    deleted = 0
    try:
        with transaction.atomic():
            try:
                # Wipe children before parents so a full restore is not blocked
                # by PROTECT foreign keys between sections.
                for key in reversed(chosen):
                    if _SECTION_SPECS[key].get("replace", True):
                        deleted += _wipe_section(key)
                for key in chosen:
                    raw = archive.read(f"data/{key}.json")
                    for obj in serializers.deserialize("json", raw):
                        obj.save()
                        loaded += 1
                media_files = _extract_media(archive)
            except IntegrityError as exc:
                raise ValueError(
                    "بازیابی این بخش به‌خاطر داده وابسته در بخش‌های دیگر ممکن نیست. "
                    "همان بخش‌ها را هم انتخاب کنید یا پشتیبان کامل بگیرید."
                ) from exc
    finally:
        archive.close()
    return RestoreResult(
        source=str(path),
        sections=chosen,
        loaded=loaded,
        deleted=deleted,
        media_files=media_files,
    )


def suggested_filename() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"erp-backup-{stamp}.zip"
