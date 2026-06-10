import csv

import pytest

from privhsd.utility_benchmark import BenchmarkError, run_utility_benchmark


try:
    import sklearn  # noqa: F401
except ModuleNotFoundError:
    HAS_SKLEARN = False
else:
    HAS_SKLEARN = True


def write_benchmark_rows(path):
    rows = [
        ("1", "Immigrants should leave now", "Immigrants should leave now", "hate"),
        ("2", "Refugees do not belong here", "Refugees do not belong here", "hate"),
        ("3", "I hate those people", "I hate those people", "hate"),
        ("4", "They should be deported", "They should be deported", "hate"),
        ("5", "Welcome to the neighborhood", "Welcome to the neighborhood", "nothate"),
        ("6", "The weather is calm today", "The weather is calm today", "nothate"),
        ("7", "Please join the public meeting", "Please join the public meeting", "nothate"),
        ("8", "Everyone deserves respect", "Everyone deserves respect", "nothate"),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "text", "privatized_text", "label"])
        writer.writerows(rows)


@pytest.mark.skipif(HAS_SKLEARN, reason="scikit-learn is installed")
def test_utility_benchmark_reports_missing_optional_dependency(tmp_path):
    source = tmp_path / "bench.csv"
    write_benchmark_rows(source)

    with pytest.raises(BenchmarkError, match=r"\.\[benchmark\]"):
        run_utility_benchmark(
            source,
            text_col="text",
            privatized_col="privatized_text",
            label_col="label",
        )


@pytest.mark.skipif(not HAS_SKLEARN, reason="requires optional benchmark extra")
def test_utility_benchmark_reports_relative_delta(tmp_path):
    source = tmp_path / "bench.csv"
    output = tmp_path / "bench.json"
    write_benchmark_rows(source)

    result = run_utility_benchmark(
        source,
        text_col="text",
        privatized_col="privatized_text",
        label_col="label",
        id_col="id",
        output_path=output,
        test_size=0.25,
        random_state=7,
    )

    assert output.exists()
    assert result["benchmark_type"] == "local_relative_utility_proxy"
    assert result["split"]["stratified"] is True
    assert result["split"]["train_count"] == 6
    assert result["split"]["dev_count"] == 2
    assert result["comparison"]["prediction_agreement"] == 1.0
    assert result["comparison"]["macro_f1_delta"] == 0.0
