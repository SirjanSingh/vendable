"""Runtime configuration.

Everything is env-driven with local-first defaults, so a clean clone runs with no `.env`
at all until it needs to touch Razorpay or Gemini.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- environment ---
    vendable_env: str = "local"
    vendable_public_base_url: str = "http://localhost:8080"

    # Comma-separated hostnames the MCP transport will accept. Empty means "localhost only",
    # which is the SDK default and correct for local work. This exists now, unused, so that
    # deploying behind a real hostname later is a config change and not a code change --
    # the SDK returns 421 Misdirected Request otherwise. See docs/research/PHASE-0.md #G.
    vendable_allowed_hosts: str = ""

    # --- storage ---
    # SQLite by default: pytest must pass with no network and no credentials.
    vendable_db_path: Path = REPO_ROOT / ".vendable" / "vendable.db"

    # --- mandate signing ---
    vendable_mandate_issuer: str = "https://vendable.local/mandates"
    vendable_mandate_private_key_pem: str = ""

    # --- Razorpay (test mode only) ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.vendable_allowed_hosts.split(",") if h.strip()]

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def is_test_mode(self) -> bool:
        """Razorpay encodes mode in the key prefix. Refuse to run against live keys."""
        return self.razorpay_key_id.startswith("rzp_test_")


settings = Settings()
