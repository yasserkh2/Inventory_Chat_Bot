from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from inventory_chatbot.config import AppConfig, ConfigurationError
from inventory_chatbot.models.api import ChatRequest


class ConfigAndModelTests(unittest.TestCase):
    def test_chat_request_rejects_blank_message(self) -> None:
        with self.assertRaises(ValidationError):
            ChatRequest(session_id="demo", message="   ", context={})

    def test_config_requires_openai_key_when_provider_is_openai(self) -> None:
        config = AppConfig(provider="openai", model_name="test-model")
        with self.assertRaises(ConfigurationError):
            config.validate_provider_credentials()

    def test_config_loads_from_env_mapping(self) -> None:
        config = AppConfig.from_env(
            {
                "PROVIDER": "azure",
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "secret",
                "AZURE_OPENAI_DEPLOYMENT": "demo-deployment",
                "MODEL_NAME": "gpt-test",
                "PORT": "9000",
            }
        )
        self.assertEqual(config.provider, "azure")
        self.assertEqual(config.port, 9000)
        self.assertEqual(config.model_name, "gpt-test")

    def test_config_can_merge_yaml_dotenv_and_env_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.yml"
            env_path = temp_path / ".env"

            config_path.write_text(
                "\n".join(
                    [
                        "provider: openai",
                        "model_name: yaml-model",
                        "port: 8100",
                        'openai_api_key: "yaml-key"',
                    ]
                ),
                encoding="utf-8",
            )
            env_path.write_text(
                "\n".join(
                    [
                        "MODEL_NAME=dotenv-model",
                        "OPENAI_API_KEY=dotenv-key",
                        "PORT=8200",
                    ]
                ),
                encoding="utf-8",
            )

            config = AppConfig.from_env(
                {"MODEL_NAME": "env-model", "OPENAI_API_KEY": "env-key"},
                env_file=env_path,
                config_file=config_path,
            )

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model_name, "env-model")
        self.assertEqual(config.openai_api_key, "env-key")
        self.assertEqual(config.port, 8200)


if __name__ == "__main__":
    unittest.main()
