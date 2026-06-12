from privhsd.rationale_checks import (
    parse_rationale_spans,
    rationale_row_report,
)


def test_hatexplain_token_range_parser_uses_token_offsets():
    spans = parse_rationale_spans(
        source="hatexplain",
        raw_value="[[1, 3]]",
        text="Alex hates Muslims today",
    )

    assert len(spans) == 1
    assert spans[0].source_kind == "token_index_range"
    assert spans[0].start == len("Alex ")
    assert spans[0].end == len("Alex hates Muslims")


def test_toxic_spans_character_offsets_merge_runs():
    spans = parse_rationale_spans(
        source="toxic_spans",
        raw_value="[1, 2, 3, 8]",
        text="abcdefghi",
    )

    assert [(span.start, span.end) for span in spans] == [(1, 4), (8, 9)]
    assert all(span.source_kind == "char_offset_range" for span in spans)


def test_toxic_spans_ignores_invalid_negative_offsets():
    spans = parse_rationale_spans(
        source="toxic_spans",
        raw_value="[-1, -2]",
        text="abcdefghi",
    )

    assert spans == []


def test_synthetic_rationale_spans_accept_char_offset_dicts():
    spans = parse_rationale_spans(
        source="synthetic_lmstudio_privhsd",
        raw_value='[{"start": 6, "end": 11, "label": "action"}]',
        text="Group leave now",
    )

    assert [(span.start, span.end, span.source_kind) for span in spans] == [
        (6, 11, "char_offset_range")
    ]


def test_rationale_report_tracks_placeholder_overlap_without_raw_text():
    report = rationale_row_report(
        row_index=1,
        row_id="r1",
        source="hatexplain",
        label="hate",
        original="Alex hates Muslims",
        protected="[PERSON] hates Muslims",
        raw_spans="[[0, 1], [1, 3]]",
    )

    assert report["has_rationale"] is True
    assert report["span_count"] == 2
    assert report["overlap_placeholder_count"] == 1
    assert report["preserved_span_count"] == 1
    assert "text" not in report
