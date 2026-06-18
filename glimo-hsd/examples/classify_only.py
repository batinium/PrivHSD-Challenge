from glimo_hsd.steps import classify_csv

result = classify_csv(
    "tests/fixtures/sample_unlabeled.csv",
    "tmp/classify_only/dehatebert_predictions.csv",
    text_col="text",
    backend="keyword",
)

print(result.path)
