"""
PR-Review Agent Config Loader
Unified loading of .env and config/settings.yaml
Supports environment variable substitution and offline mode detection
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class ConfigLoader:
    """Unified config manager, loads and merges .env + settings.yaml"""

    _instance: Optional["ConfigLoader"] = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls, project_root: Optional[str] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, project_root: Optional[str] = None):
        if self._config is not None:
            return
        if project_root:
            self._project_root = Path(project_root)
        else:
            self._project_root = Path(__file__).parent.parent.parent
        env_path = self._project_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        self._config = self._load_yaml_config()
        self._offline_mode = self._detect_offline_mode()

    def _load_yaml_config(self) -> Dict[str, Any]:
        config_path = self._project_root / "config" / "settings.yaml"
        if not config_path.exists():
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            raw_content = f.read()
        resolved_content = self._resolve_env_vars(raw_content)
        return yaml.safe_load(resolved_content) or {}

    def _resolve_env_vars(self, content: str) -> str:
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")
        return re.sub(r"\$\{(\w+)\}", replacer, content)

    def _detect_offline_mode(self) -> bool:
        mimo_key = os.environ.get("MIMO_API_KEY", "")
        mimo_url = os.environ.get("MIMO_API_URL", "")
        return not (mimo_key and mimo_url)

    @property
    def offline_mode(self) -> bool:
        return self._offline_mode

    @property
    def project_root(self) -> Path:
        return self._project_root

    def get(self, dotpath: str, default: Any = None) -> Any:
        keys = dotpath.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
            if value is None:
                return default
        return value

    def get_model_config(self, model_name: str = "mimo") -> Dict[str, Any]:
        return self.get(f"model.{model_name}", {})

    def get_agents_config(self) -> Dict[str, Any]:
        return self.get("agents", {})

    def get_flow_config(self) -> Dict[str, Any]:
        return self.get("flow", {})

    def get_rag_config(self) -> Dict[str, Any]:
        return self.get("rag", {})

    def get_web_config(self) -> Dict[str, Any]:
        return self.get("web", {})

    def get_logging_config(self) -> Dict[str, Any]:
        return self.get("logging", {})

    def get_scheduler_config(self) -> Dict[str, Any]:
        return self.get("scheduler", {})

    def get_output_config(self) -> Dict[str, Any]:
        return self.get("output", {})

    def get_debate_config(self) -> Dict[str, Any]:
        return self.get("agents.debate", {})

    def reload(self) -> None:
        self._config = None
        ConfigLoader._instance = None
        self.__init__(str(self._project_root))


def get_config(project_root: Optional[str] = None) -> ConfigLoader:
    return ConfigLoader(project_root)
