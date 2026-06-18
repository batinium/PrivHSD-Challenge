import pytest

from contextsafe_hsd.csv_pipeline import CsvPipelineError, assert_utf8_file, write_csv


def test_write_csv_outputs_valid_utf8_with_non_ascii_text(tmp_path):
    output = tmp_path / "out.csv"

    write_csv(
        output,
        [{"ID": "A", "text": "It was taken over by purple-haired SJW’s."}],
        ["ID", "text"],
    )

    output.read_bytes().decode("utf-8")


def test_assert_utf8_file_rejects_malformed_bytes(tmp_path):
    output = tmp_path / "bad.csv"
    output.write_bytes(b"ID,text\nA,SJW\xef\xbf\n")

    with pytest.raises(CsvPipelineError, match="not valid UTF-8"):
        assert_utf8_file(output)
