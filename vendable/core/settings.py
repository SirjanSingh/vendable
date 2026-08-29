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
    vendable_mandate_key_path: Path = REPO_ROOT / ".vendable" / "mandate_key.pem"
    """Ed25519 private key, in its own file.

    Deliberately not an env var: a PEM is multi-line, and squeezing one into .env means
    escaping newlines, which python-dotenv only unescapes inside double quotes. That is a
    footgun that fires as a MalformedFraming error at signing time rather than at load time.
    A file holds a PEM the way a PEM wants to be held.
    """

    # --- Razorpay (test mode only) ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # --- LLM (OpenAI) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    """Used where judgement is needed: extraction, policy compilation, negotiation."""
    openai_model_fast: str = "gpt-5-mini"
    """Used for the injection classifier, where latency matters more than nuance."""

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.vendable_allowed_hosts.split(",") if h.strip()]

    def mandate_private_key(self) -> str:
        """Read the signing key, generating one on first use.

        Generating on demand keeps `git clone && run` working with no setup step. The key
        never leaves this machine and is gitignored -- and because it persists, a mandate
        minted yesterday still verifies today, which an ephemeral per-process key would not.
        """
        path = Path(self.vendable_mandate_key_path)
        if path.exists():
            return path.read_text(encoding="utf-8")
        from vendable.mandate.ap2 import generate_keypair

        private_pem, _ = generate_keypair()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(private_pem, encoding="utf-8")
        return private_pem

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def is_test_mode(self) -> bool:
        """Razorpay encodes mode in the key prefix. Refuse to run against live keys."""
        return self.razorpay_key_id.startswith("rzp_test_")


settings = Settings()
