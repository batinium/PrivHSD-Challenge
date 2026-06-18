from pathlib import Path


def test_package_does_not_import_parent_contextsafe_hsd():
    root = Path("src/glimo_hsd")
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "contextsafe_hsd" in text:
            offenders.append(str(path))

    assert offenders == []
