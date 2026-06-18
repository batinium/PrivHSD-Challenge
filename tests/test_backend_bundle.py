import csv

from contextsafe_hsd import backend_bundle as bundle


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_backend_bundle_predicts_labels_for_unlabeled_csv(monkeypatch, tmp_path):
    source = tmp_path / "source.csv"
    bundle.write_csv(
        source,
        [{"id": "row-1", "text": "A hostile comment about immigrants.", "meta": "keep"}],
        ["id", "text", "meta"],
    )

    def fake_token_importance(*_args, **_kwargs):
        return {"status": "loaded", "path": "importance.csv", "token_rows": 0}

    def fake_scrub(input_path, output_path, *, manifest_path, audit_path, **_kwargs):
        rows, fieldnames = bundle.read_csv(input_path)
        bundle.write_csv(output_path, rows, fieldnames)
        manifest = {"pipeline": "fake", "validation": {"valid": True}}
        bundle.write_json(manifest_path, manifest)
        bundle.write_json(audit_path, {"ok": True})
        return manifest

    def fake_predictions(input_path, output_path, **_kwargs):
        rows, _fieldnames = bundle.read_csv(input_path)
        prediction_rows = [
            {
                "row_index": index,
                "row_id": row["id"],
                bundle.PREDICTION_SCORE_COL: 0.91,
                bundle.PREDICTED_LABEL_COL: 1,
                "hf_hsd_threshold": 0.5,
            }
            for index, row in enumerate(rows, start=1)
        ]
        bundle.write_csv(
            output_path,
            prediction_rows,
            [
                "row_index",
                "row_id",
                bundle.PREDICTION_SCORE_COL,
                bundle.PREDICTED_LABEL_COL,
                "hf_hsd_threshold",
            ],
        )
        return {
            "status": "generated",
            "path": str(output_path),
            "row_count": len(rows),
            "positive_rows": len(rows),
            "negative_rows": 0,
        }

    def fake_restatement_batch(batch, **_kwargs):
        return ["The comment attacks immigrants." for _row in batch], "", 0.01

    monkeypatch.setattr(bundle, "ensure_token_importance", fake_token_importance)
    monkeypatch.setattr(bundle, "run_final_csv_pipeline", fake_scrub)
    monkeypatch.setattr(bundle, "ensure_hsd_predictions", fake_predictions)
    monkeypatch.setattr(bundle, "request_restatement_batch", fake_restatement_batch)

    manifest = bundle.run_backend_bundle(
        source,
        tmp_path / "out",
        text_col="text",
        id_col="id",
        label_col="hs",
    )

    restated_rows = read_rows(tmp_path / "out" / "source.restated.csv")
    annotated_rows = read_rows(tmp_path / "out" / "source.restated.annotated.csv")
    restatement_input_rows = read_rows(tmp_path / "out" / "source.restatement_input.csv")

    assert manifest["classification"]["label_source"] == "predicted"
    assert manifest["restatement_input"]["label_source"] == "predicted"
    assert list(restated_rows[0]) == ["id", "text", "meta"]
    assert restated_rows[0]["text"] == "The comment attacks immigrants."
    assert restatement_input_rows[0]["hs"] == "1"
    assert restatement_input_rows[0]["hs_predicted"] == "1"
    assert annotated_rows[0]["hs"] == "1"
    assert annotated_rows[0]["hs_predicted"] == "1"
    assert annotated_rows[0]["hf_hsd_score"] == "0.91"
    assert annotated_rows[0]["source_text"] == "A hostile comment about immigrants."
    assert manifest["validation"]["valid"] is True
