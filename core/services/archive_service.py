from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
import zipfile, datetime as dt, logging

from django.conf import settings
from django.utils.text import slugify
from apps.payroll.models import PayrollPeriod

logger = logging.getLogger(__name__)

class ArchiveServiceError(Exception):
    def __init__(self, message: str, *, context: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
    def get_context(self) -> dict: return self.context
    
@dataclass(frozen=True)
class ArchiveResult:
    archive_path: Path
    files_count: int
    
class ArchiveService:
    """Archive PDF and CSV files to MEDIA_ARCHIVES_DIR, respecting the form MEDIA_ARCHIVES_DIR/{period.label}/<label>-<timestamp>.zip"""
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = Path(base_dir or settings.MEDIA_ARCHIVES_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ArchiveService initialized with directory: {self.base_dir}")

    def _archive_path(self, period: PayrollPeriod, *, label: str) -> Path:
        period_dir = self.base_dir / period.label
        period_dir.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = period_dir / f"{slugify(label)}-{ts}.zip"
        logger.debug(f"Generated archive path: {archive_path}") 
        return archive_path

    def archive_files(self, files: Iterable[Path], *, label: str, period: PayrollPeriod) -> ArchiveResult:
        file_list = [Path(p) for p in files if Path(p).exists()]
        if not file_list:
            logger.warning(f"No files to archive for {label}, period {period.label}")
            raise ArchiveServiceError("No files to archive.", context={"label": label, "period": period.id})
        archive_path = self._archive_path(period, label=label)
        try:
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for p in file_list:
                    zf.write(str(p), p.name)
                    logger.debug(f"Added to archive: {p.name}")
        except Exception as e:
            logger.error(f"Failed to create archive: {e}")
            raise ArchiveServiceError(f"Failed to create archive: {str(e)}", context={"archive_path": str(archive_path)}) from e
        
        logger.info(
            f"Archive created successfully",
            extra={"archive": str(archive_path), "count": len(file_list)})
        
        return ArchiveResult(archive_path=archive_path, files_count=len(file_list))