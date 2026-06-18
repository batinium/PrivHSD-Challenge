"""Full CSV pipeline orchestration."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .io import (
    CsvError,
    copy_file,
    read_csv,
    read_json,
    sha256_file,
    stable_hash,
    write_csv,
    write_json,
)
from .results import PipelineResult, StepResult
from .schemas.columns import (
    PREDICTED_LABEL_COL,
    PREDICTION_SCORE_COL,
    resolve_label_col,
)
from .schemas.manifest import build_manifest
from .steps.classify import classify_csv, write_label_predictions
from .steps.deviation_audit import audit_restatements
from .steps.final_scrub import final_scrub_csv
from .steps.pii import scrub_csv
from .steps.restate import restate_csv
from .steps.token_importance import generate_token_importances


def _default_output_dir(input_csv: Path) -> Path:
    return input_csv.with_suffix("").parent / f"{input_csv.stem}.glimo_hsd"


def _paths(output_dir: Path) -> dict[str, Path]:
    return {
        "source": output_dir / "source.csv",
        "scrubbed": output_dir / "scrubbed.csv",
        "predictions": output_dir / "dehatebert_predictions.csv",
        "importances": output_dir / "token_importances.csv",
        "restatement_input": output_dir / "restatement_input.csv",
        "restated": output_dir / "restated.csv",
        "restated_annotated": output_dir / "restated.annotated.csv",
        "final_scrubbed": output_dir / "final_scrubbed.csv",
        "audit": output_dir / "deviation_audit.csv",
        "manifest": output_dir / "manifest.json",
    }


def _config_hash(config: PipelineConfig) -> str:
    return stable_hash(asdict(config))


def _cache_hit(manifest_path: Path, *, input_hash: str, config_hash: str) -> bool:
    if not manifest_path.exists():
        return False
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return False
    return (
        manifest.get("input_hash") == input_hash
        and manifest.get("config_hash") == config_hash
    )


def _prediction_rows(path: Path) -> dict[str, dict[str, str]]:
    rows, _fieldnames = read_csv(path)
    return {
        str(row.get("row_index") or index): row
        for index, row in enumerate(rows, start=1)
    }


def _build_restatement_input(
    scrubbed_csv: Path,
    output_csv: Path,
    *,
    predictions_csv: Path,
    label_col: str,
    resolved_label_col: str | None,
) -> tuple[StepResult, list[str]]:
    rows, fieldnames = read_csv(scrubbed_csv)
    if resolved_label_col is not None:
        if scrubbed_csv != output_csv:
            write_csv(output_csv, rows, fieldnames)
        return (
            StepResult(
                name="restatement_input",
                status="provided",
                path=output_csv,
                metadata={
                    "label_col": resolved_label_col,
                    "label_source": "provided",
                    "sha256": sha256_file(output_csv),
                },
            ),
            fieldnames,
        )
    predictions = _prediction_rows(predictions_csv)
    helper_columns = [label_col]
    if label_col != PREDICTED_LABEL_COL:
        helper_columns.append(PREDICTED_LABEL_COL)
    helper_columns.append(PREDICTION_SCORE_COL)
    internal_fields = [
        *fieldnames,
        *[col for col in helper_columns if col not in fieldnames],
    ]
    output_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        prediction = predictions.get(str(index))
        if prediction is None:
            raise CsvError(f"missing classifier prediction for row {index}")
        out = dict(row)
        label = str(prediction.get(PREDICTED_LABEL_COL, "") or "")
        out[label_col] = label
        if label_col != PREDICTED_LABEL_COL:
            out[PREDICTED_LABEL_COL] = label
        out[PREDICTION_SCORE_COL] = str(prediction.get(PREDICTION_SCORE_COL, "") or "")
        output_rows.append(out)
    write_csv(output_csv, output_rows, internal_fields)
    return (
        StepResult(
            name="restatement_input",
            status="complete",
            path=output_csv,
            metadata={
                "label_col": label_col,
                "label_source": "predicted",
                "helper_columns": helper_columns,
                "sha256": sha256_file(output_csv),
            },
        ),
        fieldnames,
    )


def process_csv(
    input_csv: str | Path,
    *,
    config: PipelineConfig | None = None,
) -> PipelineResult:
    cfg = config or PipelineConfig()
    source_path = Path(input_csv)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    output_dir = (
        Path(cfg.output_dir)
        if cfg.output_dir is not None
        else _default_output_dir(source_path)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _paths(output_dir)
    input_hash = sha256_file(source_path)
    config_hash = _config_hash(cfg)
    if not cfg.force and _cache_hit(
        paths["manifest"],
        input_hash=input_hash,
        config_hash=config_hash,
    ):
        return PipelineResult.from_output_dir(output_dir)

    rows, fieldnames = read_csv(source_path)
    if cfg.text_col not in fieldnames:
        raise CsvError(f"missing text column {cfg.text_col!r}")
    copy_file(source_path, paths["source"])

    steps: dict[str, StepResult] = {}
    steps["pii_scrub"] = scrub_csv(
        paths["source"],
        paths["scrubbed"],
        text_col=cfg.text_col,
    )
    scrubbed_rows, scrubbed_fields = read_csv(paths["scrubbed"])
    del scrubbed_rows
    resolved_label = resolve_label_col(scrubbed_fields, cfg.label_col)
    label_col = resolved_label or cfg.label_col or "hs"
    if resolved_label is not None:
        steps["classification"] = write_label_predictions(
            paths["scrubbed"],
            paths["predictions"],
            label_col=resolved_label,
            id_col=cfg.id_col,
        )
    else:
        steps["classification"] = classify_csv(
            paths["scrubbed"],
            paths["predictions"],
            text_col=cfg.text_col,
            id_col=cfg.id_col,
            model_id=cfg.model_id,
            model_revision=cfg.model_revision,
            backend=cfg.classifier_backend,
            threshold=cfg.threshold,
            device=cfg.device,
            batch_size=cfg.batch_size,
            max_length=cfg.max_length,
        )
    steps["token_importance"] = generate_token_importances(
        paths["scrubbed"],
        paths["importances"],
        text_col=cfg.text_col,
        id_col=cfg.id_col,
        model_id=cfg.model_id,
        model_revision=cfg.model_revision,
        backend=cfg.classifier_backend,
        threshold=cfg.threshold,
        device=cfg.device,
        batch_size=cfg.batch_size,
        max_length=cfg.max_length,
        protect_threshold=cfg.token_protect_threshold,
        enabled=cfg.token_importance,
    )
    steps["restatement_input"], public_fieldnames = _build_restatement_input(
        paths["scrubbed"],
        paths["restatement_input"],
        predictions_csv=paths["predictions"],
        label_col=label_col,
        resolved_label_col=resolved_label,
    )
    steps["restatement"] = restate_csv(
        paths["restatement_input"],
        paths["restated"],
        annotated_csv=paths["restated_annotated"],
        text_col=cfg.text_col,
        id_col=cfg.id_col,
        label_col=label_col,
        config=cfg.restatement_config(),
        output_fieldnames=public_fieldnames,
    )
    public_restated = paths["restated"]
    if cfg.final_scrub:
        steps["final_scrub"] = final_scrub_csv(
            paths["restated"],
            paths["final_scrubbed"],
            text_col=cfg.text_col,
        )
        public_restated = paths["final_scrubbed"]
    else:
        steps["final_scrub"] = StepResult(
            name="final_scrub",
            status="skipped",
            path=None,
            metadata={"reason": "disabled"},
        )
    steps["deviation_audit"] = audit_restatements(
        paths["source"],
        public_restated,
        paths["audit"],
        text_col=cfg.text_col,
        id_col=cfg.id_col,
        label_col=resolved_label,
    )
    manifest = build_manifest(
        output_dir=output_dir,
        input_hash=input_hash,
        config_hash=config_hash,
        source_path=source_path,
        text_col=cfg.text_col,
        label_col=resolved_label,
        model_id=cfg.model_id,
        model_revision=cfg.model_revision,
        steps=steps,
        outputs={
            "source_csv": paths["source"],
            "scrubbed_csv": paths["scrubbed"],
            "predictions_csv": paths["predictions"],
            "importances_csv": paths["importances"],
            "restatement_input_csv": paths["restatement_input"],
            "restated_csv": public_restated,
            "raw_restated_csv": paths["restated"],
            "audit_csv": paths["audit"],
            "manifest_json": paths["manifest"],
        },
    )
    manifest["row_count"] = len(rows)
    manifest["force"] = cfg.force
    write_json(paths["manifest"], manifest)
    return PipelineResult(
        source_csv=paths["source"],
        scrubbed_csv=paths["scrubbed"],
        predictions_csv=paths["predictions"],
        importances_csv=paths["importances"],
        restatement_input_csv=paths["restatement_input"],
        restated_csv=public_restated,
        audit_csv=paths["audit"],
        manifest_json=paths["manifest"],
        output_dir=output_dir,
        final_scrubbed_csv=paths["final_scrubbed"] if cfg.final_scrub else None,
        raw_restated_csv=paths["restated"],
    )
