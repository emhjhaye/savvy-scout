"""Single config layer. Static settings load from .env; tunable rule values
(owner map, CPV lists, keyword lists, the scale filter) are DB-backed, see
db/seed_config.py, so they can be corrected without a code change."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_path: str
    lookback_days: int
    find_a_tender_base_url: str
    contracts_finder_base_url: str
    flask_secret_key: str | None
    ms_graph_tenant_id: str | None
    ms_graph_client_id: str | None
    ms_graph_client_secret: str | None
    ms_graph_sender_upn: str | None
    anthropic_api_key: str | None = None
    # 2026-07-30: Phase 2 scope reads can run against either provider --
    # added when Anthropic credit ran out and OpenAI was the fallback.
    # SCOPE_READ_PROVIDER picks which; only that provider's key needs to be
    # set for Phase 2 to be "ready" (see scope_read_ready below).
    openai_api_key: str | None = None
    scope_read_provider: str = "anthropic"

    @property
    def graph_configured(self) -> bool:
        return bool(
            self.ms_graph_tenant_id and self.ms_graph_client_id
            and self.ms_graph_client_secret and self.ms_graph_sender_upn
        )

    @property
    def scope_read_ready(self) -> bool:
        if self.scope_read_provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.anthropic_api_key)


def load_settings() -> Settings:
    return Settings(
        db_path=os.environ.get("SAVVY_SCOUT_DB_PATH", "savvy_scout.db"),
        lookback_days=int(os.environ.get("SAVVY_SCOUT_LOOKBACK_DAYS", "7")),
        find_a_tender_base_url=os.environ.get(
            "FIND_A_TENDER_BASE_URL", "https://www.find-tender.service.gov.uk/api/1.0"
        ),
        contracts_finder_base_url=os.environ.get(
            "CONTRACTS_FINDER_BASE_URL",
            "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search",
        ),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
        scope_read_provider=os.environ.get("SCOPE_READ_PROVIDER", "anthropic").strip().lower(),
        flask_secret_key=os.environ.get("FLASK_SECRET_KEY") or None,
        ms_graph_tenant_id=os.environ.get("MS_GRAPH_TENANT_ID") or None,
        ms_graph_client_id=os.environ.get("MS_GRAPH_CLIENT_ID") or None,
        ms_graph_client_secret=os.environ.get("MS_GRAPH_CLIENT_SECRET") or None,
        ms_graph_sender_upn=os.environ.get("MS_GRAPH_SENDER_UPN") or None,
    )
