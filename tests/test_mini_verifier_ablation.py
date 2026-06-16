import json

from contextsafe_hsd.mini_verifier_ablation import (
    ClassificationItem,
    EvalRow,
    TaskRun,
    VerifierItem,
    binary_metrics,
    cue_bearing_negative,
    normalize_classifier_items,
    parse_json_object,
    run_verifier,
    select_candidates,
    summarize_candidate,
)


def content_response(items):
    return {"choices": [{"message": {"content": json.dumps({"items": items})}}]}


def eval_row(row_id, *, case_type, gold, main, text="plain text", reasons="none"):
    return EvalRow(
        id=row_id,
        case_type=case_type,
        gold_hs="1" if gold else "0",
        main_hate="1" if main else "0",
        main_hsd_reasons=reasons,
        review_needed="False",
        parse_status="ok",
        source_text=text,
        cleaned_text=text,
    )


def verifier_item(row_id, *, decision, suggested_label, reason="other"):
    return VerifierItem(
        row_id=row_id,
        decision=decision,
        suggested_label=suggested_label,
        reason=reason,
        parse_status="ok",
    )


def classifier_item(row_id, *, hate, reason="other"):
    return ClassificationItem(
        row_id=row_id,
        hate=hate,
        reason=reason,
        parse_status="ok",
    )


def test_parse_json_object_accepts_code_fences_and_embedded_json():
    assert parse_json_object('```json\n{"items": []}\n```') == {"items": []}
    assert parse_json_object('prefix {"items": []} suffix') == {"items": []}


def test_select_candidates_respects_inventory_order_and_probe():
    candidates, probes = select_candidates(
        [
            "mistralai/ministral-3-3b",
            "qwen/qwen3-4b-2507",
            "gemma-4-e4b-uncensored-hauhaucs-aggressive",
        ],
        include_uncensored_probe=True,
    )

    assert candidates == ["qwen/qwen3-4b-2507", "mistralai/ministral-3-3b"]
    assert probes == ["gemma-4-e4b-uncensored-hauhaucs-aggressive"]


def test_cue_bearing_negative_uses_cleaned_text_identity_cues():
    row = eval_row("1", case_type="FN", gold=True, main=False, text="Muslims should leave.")
    control = eval_row("2", case_type="TN", gold=False, main=False, text="The meeting starts soon.")

    assert cue_bearing_negative(row) is True
    assert cue_bearing_negative(control) is False


def test_binary_metrics_reports_confusion_and_scores():
    metrics = binary_metrics([True, True, False, False], [True, False, True, False])

    assert metrics["accuracy"] == 0.5
    assert metrics["balanced_accuracy"] == 0.5
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["confusion"] == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}


def test_classifier_normalization_can_recover_abbreviated_ids_by_position():
    rows = [eval_row("REDDIT_407", case_type="FP", gold=False, main=True)]
    items = normalize_classifier_items(
        {
            "items": [
                {
                    "id": "RE...",
                    "hate": False,
                    "reason": "ambiguous_false",
                }
            ]
        },
        input_rows=rows,
        allow_positional_ids=True,
    )

    assert items[0].row_id == "REDDIT_407"
    assert items[0].hate is False


def test_summarize_candidate_scores_combined_router_without_small_direct_flips():
    rows = [
        eval_row("fp", case_type="FP", gold=False, main=True),
        eval_row("fn", case_type="FN", gold=True, main=False, text="Muslims should leave."),
        eval_row("tp", case_type="TP", gold=True, main=True),
        eval_row("tn", case_type="TN", gold=False, main=False),
    ]
    direct_run = TaskRun(
        model_id="small",
        task="direct_classifier",
        rows=tuple(
            [
                classifier_item("fp", hate=True),
                classifier_item("fn", hate=True),
                classifier_item("tp", hate=True),
                classifier_item("tn", hate=False),
            ]
        ),
        elapsed_seconds=4.0,
        request_count=1,
        fallback_count=0,
    )
    verifier_run = TaskRun(
        model_id="small",
        task="verifier",
        rows=tuple(
            [
                verifier_item("fp", decision="disagree", suggested_label=False),
                verifier_item("fn", decision="uncertain", suggested_label=True),
                verifier_item("tp", decision="agree", suggested_label=True),
                verifier_item("tn", decision="disagree", suggested_label=True),
            ]
        ),
        elapsed_seconds=4.0,
        request_count=1,
        fallback_count=0,
    )

    summary = summarize_candidate(rows, direct_run=direct_run, verifier_run=verifier_run)
    combined = summary["strategies"]["combined_router"]

    assert combined["fp_rescue_rate"] == 1.0
    assert combined["fn_rescue_rate"] == 1.0
    assert combined["tp_disagree_rate"] == 0.0
    assert combined["tn_route_rate"] == 0.0
    assert combined["estimated_production_overhead"] == 0.5
    assert combined["direct_flip_metrics"]["confusion"] == {
        "tp": 1,
        "tn": 2,
        "fp": 0,
        "fn": 1,
    }


def test_run_verifier_retries_malformed_batch_per_row():
    calls = []

    def fake_request(payload, _timeout):
        calls.append(payload)
        rows = json.loads(payload["messages"][1]["content"])["items"]
        if len(calls) == 1:
            return content_response([{"id": rows[0]["id"], "decision": "agree"}])
        return content_response(
            [
                {
                    "id": rows[0]["id"],
                    "decision": "agree",
                    "suggested_label": rows[0]["main_label"],
                    "reason": "other",
                }
            ]
        )

    result = run_verifier(
        rows=[
            eval_row("1", case_type="TP", gold=True, main=True),
            eval_row("2", case_type="TN", gold=False, main=False),
        ],
        model_id="small",
        endpoint="http://local.test/v1/chat/completions",
        timeout=10,
        batch_size=2,
        request_callable=fake_request,
    )

    assert result.parse_success_rate == 1.0
    assert result.fallback_count == 2
    assert result.request_count == 3
    assert [row.row_id for row in result.rows] == ["1", "2"]
