from glimo_hsd import PipelineConfig


def test_pipeline_config_defaults_to_published_model():
    config = PipelineConfig()

    assert config.model_id == "batinium/glimo-dehatebert-hsd"
    assert config.model_config().backend == "hf"
    assert config.restatement_config().backend == "none"
