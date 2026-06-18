from glimo_hsd.steps import audit_restatements

result = audit_restatements(
    "tests/fixtures/sample_5.csv",
    "tests/fixtures/sample_5.csv",
    "tmp/audit/deviation_audit.csv",
    text_col="text",
    label_col="hs",
)

print(result.path)
