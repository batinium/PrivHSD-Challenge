import csv
import json

from contextsafe_hsd.cli import build_parser
from contextsafe_hsd.lm_context_benchmark import (
    BenchmarkRequestError,
    parse_binary_tags_mode,
    parse_json_mode,
    parse_tagged_mode,
    run_lm_context_benchmark,
)


def write_rows(path):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["id", "text", "label", "source", "target", "target_categories"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "id": "1",
                "text": "Do not attack Muslims.",
                "label": "not_hate",
                "source": "hatecheck",
                "target": "Muslims",
                "target_categories": "religion",
            }
        )


def test_benchmark_lm_context_command_is_registered():
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark-lm-context",
            "--input",
            "input.csv",
            "--text-col",
            "text",
            "--model",
            "local-model",
        ]
    )

    assert args.command == "benchmark-lm-context"
    assert args.model == "local-model"


def test_lm_context_parsers_accept_fallback_formats():
    parsed_json = parse_json_mode(
        '{"context_tags":["protected_target"],'
        '"protected_phrases":["Muslims"],"maskable_phrases":[],'
        '"uncertainty":"low","reason_codes":["target"]}'
    )
    parsed_tagged = parse_tagged_mode(
        "TAGS: protected_target, negated_hate\n"
        "PROTECT: Muslims; do not\n"
        "MASKABLE: username\n"
        "UNCERTAINTY: medium\n"
        "REASONS: negation_present"
    )
    parsed_binary = parse_binary_tags_mode(
        "protected_target=yes\nnegation=yes\nprotect=Muslims; do not\nmask=user"
    )

    assert parsed_json["context_tags"] == ["protected_target"]
    assert "negated_hate" in parsed_tagged["context_tags"]
    assert parsed_binary["protected_phrase_count"] == 2


def test_lm_context_json_parser_accepts_common_wrappers_and_variants():
    fenced = parse_json_mode(
        '```json\n{"protected_target": true, "protect": ["Muslims"], '
        '"mask": [], "uncertainty": "low"}\n```'
    )
    array_tags = parse_json_mode('["protected-target", "negation"]')
    explicit_empty = parse_json_mode(
        '{"context_tags": [], "protected_phrases": [], '
        '"maskable_phrases": [], "uncertainty": "low"}'
    )

    assert fenced["context_tags"] == ["protected_target"]
    assert fenced["protected_phrase_count"] == 1
    assert array_tags["context_tags"] == ["protected_target", "negated_hate"]
    assert explicit_empty["context_tags"] == []
    assert explicit_empty["uncertainty"] == "low"


def test_lm_context_benchmark_writes_blocked_report(tmp_path, monkeypatch):
    source = tmp_path / "rows.csv"
    output = tmp_path / "lm.json"
    write_rows(source)

    def fake_post(**kwargs):
        raise BenchmarkRequestError("connection_error", "connection refused")

    monkeypatch.setattr(
        "contextsafe_hsd.lm_context_benchmark.post_chat_completion",
        fake_post,
    )

    result = run_lm_context_benchmark(
        source,
        text_col="text",
        id_col="id",
        source_col="source",
        label_col="label",
        endpoint="http://127.0.0.1:1234/v1/chat/completions",
        model="local-model",
        sample_size=1,
        output_path=output,
        timeout=0.01,
    )

    written = json.loads(output.read_text(encoding="utf-8"))
    assert result == written
    assert result["status"] == "blocked"
    assert result["skip_reason"] == "endpoint_unreachable"
    assert result["rows"][0]["row_id"] == "1"
    assert "Do not attack" not in output.read_text(encoding="utf-8")
