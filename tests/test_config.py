import os, pytest, yaml
from pathlib import Path

@pytest.fixture(autouse=True)
def reset():
    from src.core.config_loader import ConfigLoader
    ConfigLoader._instance = None; ConfigLoader._config = None
    yield
    ConfigLoader._instance = None; ConfigLoader._config = None

@pytest.fixture
def proj(tmp_path):
    (tmp_path / "config").mkdir(); (tmp_path / "config" / "prompts").mkdir()
    return tmp_path

class TestConfigLoader:
    def test_load_yaml(self, proj):
        (proj / "config" / "settings.yaml").write_text(yaml.dump({"web": {"port": 9000}}), encoding="utf-8")
        from src.core.config_loader import ConfigLoader
        assert ConfigLoader(str(proj)).get("web.port") == 9000

    def test_env_substitution(self, proj):
        os.environ["TEST_KEY"] = "sk-test"
        (proj / "config" / "settings.yaml").write_text(yaml.dump({"model": {"key": "${TEST_KEY}"}}), encoding="utf-8")
        from src.core.config_loader import ConfigLoader
        assert ConfigLoader(str(proj)).get("model.key") == "sk-test"
        del os.environ["TEST_KEY"]

    def test_offline_detection(self, proj):
        os.environ.pop("MIMO_API_KEY", None); os.environ.pop("MIMO_API_URL", None)
        (proj / "config" / "settings.yaml").write_text("model: {}", encoding="utf-8")
        from src.core.config_loader import ConfigLoader
        assert ConfigLoader(str(proj)).offline_mode is True

    def test_default_value(self, proj):
        (proj / "config" / "settings.yaml").write_text("model: {}", encoding="utf-8")
        from src.core.config_loader import ConfigLoader
        assert ConfigLoader(str(proj)).get("no.key", "default") == "default"

    def test_singleton(self, proj):
        (proj / "config" / "settings.yaml").write_text("model: {}", encoding="utf-8")
        from src.core.config_loader import ConfigLoader
        assert ConfigLoader(str(proj)) is ConfigLoader(str(proj))
