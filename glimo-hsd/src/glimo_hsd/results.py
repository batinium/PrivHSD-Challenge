"""Result objects returned by package APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StepResult:
    name: str
    status: str
    path: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_manifest(self, *, root: Path | None = None) -> dict[str, Any]:
        path: str | None = None
        if self.path is not None:
            path = str(self.path.relative_to(root)) if root else str(self.path)
        return {
            "status": self.status,
            "path": path,
            **self.metadata,
        }


@dataclass(frozen=True)
class PipelineResult:
    source_csv: Path
    scrubbed_csv: Path
    predictions_csv: Path
    importances_csv: Path
    restatement_input_csv: Path
    restated_csv: Path
    audit_csv: Path
    manifest_json: Path
    output_dir: Path
    final_scrubbed_csv: Path | None = None
    raw_restated_csv: Path | None = None

    @classmethod
    def from_output_dir(cls, output_dir: Path) -> PipelineResult:
        final_scrubbed = output_dir / "final_scrubbed.csv"
        restated = (
            final_scrubbed if final_scrubbed.exists() else output_dir / "restated.csv"
        )
        return cls(
            source_csv=output_dir / "source.csv",
            scrubbed_csv=output_dir / "scrubbed.csv",
            predictions_csv=output_dir / "dehatebert_predictions.csv",
            importances_csv=output_dir / "token_importances.csv",
            restatement_input_csv=output_dir / "restatement_input.csv",
            restated_csv=restated,
            audit_csv=output_dir / "deviation_audit.csv",
            manifest_json=output_dir / "manifest.json",
            output_dir=output_dir,
            final_scrubbed_csv=final_scrubbed if final_scrubbed.exists() else None,
            raw_restated_csv=output_dir / "restated.csv",
        )
