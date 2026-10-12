"""Environment parsing and authentication compatibility."""

import base64
import os
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import pytest
from httpx2 import Response

from app.config import ENV_FILE, Settings, load_local_environment
from tests.support import ServiceContext


class TestLocalEnvironment:
    """The Hugging Face token from dotenv reaches the process before model download."""

    def test_project_dotenv_does_not_override_the_process(self) -> None:
        """Keep variables already exported by the shell or the container."""
        with patch("app.config.load_dotenv") as loader:
            load_local_environment()
        loader.assert_called_once_with(ENV_FILE, override=False)

    def test_blank_token_is_removed(self) -> None:
        """Drop an empty token so Hub clients do not send a blank bearer credential."""
        with (
            patch("app.config.load_dotenv"),
            patch.dict(os.environ, {"HF_TOKEN": "  "}),
        ):
            load_local_environment()
            assert "HF_TOKEN" not in os.environ

    def test_token_whitespace_is_stripped(self) -> None:
        """Trim the token before the Hub client reads it from the environment."""
        with (
            patch("app.config.load_dotenv"),
            patch.dict(os.environ, {"HF_TOKEN": " hf_example "}),
        ):
            load_local_environment()
            assert os.environ["HF_TOKEN"] == "hf_example"


class TestSettings:
    """Configuration defaults and parsing remain compatible with Docker deployments."""

    def test_defaults(self) -> None:
        """Preserve the deployment defaults when no environment values are supplied."""
        assert Settings.from_environment({}) == Settings()

    def test_environment_is_read_when_requested(self) -> None:
        """Read the current environment when no explicit mapping is provided."""
        with patch.dict("os.environ", {"DEVICE": "mps"}, clear=True):
            assert Settings.from_environment().device == "mps"

    def test_explicit_empty_environment_ignores_process_environment(self) -> None:
        """Treat an empty mapping as an intentional configuration source."""
        with patch.dict("os.environ", {"DEVICE": "mps"}):
            assert Settings.from_environment({}).device == "cpu"

    def test_comma_separated_configuration(self) -> None:
        """Trim list entries and preserve password colons across all deployment settings."""
        settings = Settings.from_environment(
            {
                "API_KEYS": " first, , second ",
                "BASIC_AUTH": " invalid, user : pass:word ",
                "MODELS": " english, multilingual, ",
                "DEVICE": "mps",
                "MODEL_ID": "local",
                "MODEL_SUBFOLDER": "weights",
                "MAX_BULK_ITEMS": " 2 ",
            }
        )
        assert settings == Settings(
            api_keys=("first", "second"),
            basic_auth=(("user", "pass:word"),),
            models=("english", "multilingual"),
            device="mps",
            model_id="local",
            model_subfolder="weights",
            max_bulk_items=2,
        )

    @pytest.mark.parametrize("value", ["", " ", "0"])
    def test_unlimited_bulk_values(self, value: str) -> None:
        """Interpret missing, blank and zero bulk limits as unlimited."""
        assert Settings.from_environment({"MAX_BULK_ITEMS": value}).max_bulk_items is None

    def test_invalid_bulk_limit_fails_at_configuration(self) -> None:
        """Reject a malformed batch limit before constructing the application."""
        with pytest.raises(ValueError):
            Settings.from_environment({"MAX_BULK_ITEMS": "invalid"})

    def test_configuration_is_immutable(self) -> None:
        """Prevent configuration changes after the settings object has been constructed."""
        with pytest.raises(FrozenInstanceError):
            Settings().__setattr__("device", "mps")

    @pytest.mark.parametrize(
        "settings, methods",
        [
            (Settings(), []),
            (Settings(api_keys=("key",)), ["apikey"]),
            (Settings(basic_auth=(("u", "p"),)), ["basic"]),
            (Settings(api_keys=("key",), basic_auth=(("u", "p"),)), ["apikey", "basic"]),
        ],
    )
    def test_authentication_metadata(self, settings: Settings, methods: list[str]) -> None:
        """Report exactly the configured authentication methods in the public health metadata."""
        assert settings.auth_enabled == bool(methods)
        assert settings.auth_methods == methods


class TestAuthentication:
    """Alternative authentication methods grant access without requiring both."""

    SETTINGS = Settings(api_keys=("secret",), basic_auth=(("user", "pass"), ("josé", "pass:word")))

    @staticmethod
    def request(settings: Settings, authorization: str | None, key: str | None) -> Response:
        """Call a protected route with the given Authorization and X-API-Key headers."""
        headers = {"Authorization": authorization, "X-API-Key": key}
        present = {name: value for name, value in headers.items() if value is not None}
        response: Response = ServiceContext(settings).client().get("/presets", headers=present)
        return response

    @pytest.mark.parametrize(
        "authorization, key",
        [
            (None, "secret"),
            (None, " secret "),
            ("bEaReR secret", None),
            ("Bearer  secret ", "wrong"),
            ("Basic dXNlcjpwYXNz", None),
            ("Basic dXNlcjpwYXNz", "wrong"),
            ("basic " + base64.b64encode("josé:pass:word".encode()).decode(), None),
            ("unsupported", "secret"),
            ("Basic ###", "secret"),
        ],
    )
    def test_valid_alternatives(self, authorization: str | None, key: str | None) -> None:
        """Accept any configured method, whatever the other header carries."""
        assert self.request(self.SETTINGS, authorization, key).status_code == 200

    @pytest.mark.parametrize(
        "authorization, key",
        [
            (None, None),
            (None, "wrong"),
            ("Bearer wrong", None),
            ("Bearer", None),
            ("Digest secret", None),
            ("Basic ###", None),
            ("Basic a", None),
            ("Basic /w==", None),
            ("Basic dXNlcjp3cm9uZw==", None),
            ("Basic c2VjcmV0", None),
        ],
    )
    def test_invalid_credentials(self, authorization: str | None, key: str | None) -> None:
        """Reject missing, malformed or incorrect credentials with the documented challenge."""
        response = self.request(self.SETTINGS, authorization, key)
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing credentials"}
        assert response.headers["www-authenticate"] == 'Basic realm="laya", Bearer'

    def test_disabled_authentication_allows_missing_credentials(self) -> None:
        """Allow unauthenticated access when the deployment configures no credentials."""
        assert self.request(Settings(), None, None).status_code == 200
