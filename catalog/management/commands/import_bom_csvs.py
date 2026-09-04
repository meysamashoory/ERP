"""Load Bom Version CSV samples into product-data BOM tabs."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.bom_import import import_bom_paths


class Command(BaseCommand):
    help = "Import Bom Version CSV files into دیتای محصولات BOM tabs"

    def add_arguments(self, parser):
        parser.add_argument(
            "paths",
            nargs="*",
            type=str,
            help="CSV file paths (default: catalog/fixtures/bom_samples/*.csv)",
        )
        parser.add_argument(
            "--no-sync-relational",
            action="store_true",
            help="Skip Product / ProductBomLine sync from parts BOM",
        )

    def handle(self, *args, **options):
        paths = [Path(p) for p in (options.get("paths") or [])]
        if not paths:
            sample_dir = Path(__file__).resolve().parents[2] / "fixtures" / "bom_samples"
            paths = sorted(sample_dir.glob("*.csv"))
        if not paths:
            raise CommandError("هیچ فایل CSV برای ورود پیدا نشد.")

        for p in paths:
            if not p.is_file():
                raise CommandError(f"فایل یافت نشد: {p}")

        results = import_bom_paths(
            paths, sync_relational=not options["no_sync_relational"]
        )
        for r in results:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{r.file_kind} → {r.level_id or '—'} : {r.rows_loaded} ردیف"
                    f" (محصول={r.products_ensured}, BOM خط={r.bom_lines_synced})"
                    + (f" · {r.notes}" if r.notes else "")
                )
            )
