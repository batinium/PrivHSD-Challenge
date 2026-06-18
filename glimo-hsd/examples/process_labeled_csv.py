from glimo_hsd import PipelineConfig, process_csv

result = process_csv(
    "tests/fixtures/sample_5.csv",
    config=PipelineConfig(
        text_col="text",
        label_col="hs",
        classifier_backend="keyword",
        restatement_backend="none",
        output_dir="tmp/example_labeled",
        final_scrub=True,
    ),
)

print(result.restated_csv)
