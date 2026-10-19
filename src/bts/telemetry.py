"""OpenTelemetry traces, metrics and logs to Application Insights.

The Agent Framework emits ``invoke_agent``, ``chat`` and ``execute_tool`` spans per crew run
once instrumentation is enabled; the Azure Monitor distro also instruments FastAPI and
logging. Connect the same Application Insights resource to the Foundry project and the
traces show up in the Foundry portal too.
"""

from __future__ import annotations

import logging

from bts import __version__
from bts.config import Settings

SERVICE_NAME = "beyond-the-scoreline"
# The exporter and the SDK's HTTP policy log every transmission at INFO; with the logging
# handler attached those lines would be exported again, one transmission per second forever.
QUIET_LOGGERS = (
    "azure.monitor.opentelemetry.exporter",
    "azure.core.pipeline.policies.http_logging_policy",
)
log = logging.getLogger(__name__)
_configured = False


def configure_telemetry(settings: Settings) -> bool:
    """Turn telemetry on when a connection string is set; a no-op (and no import) otherwise."""
    global _configured
    if not settings.app_insights_connection_string:
        log.info("telemetry: off (APPLICATIONINSIGHTS_CONNECTION_STRING unset)")
        return False
    if _configured:
        return True
    from agent_framework.observability import create_resource, enable_instrumentation
    from azure.monitor.opentelemetry import configure_azure_monitor

    resource = create_resource(service_name=SERVICE_NAME, service_version=__version__)
    configure_azure_monitor(
        connection_string=settings.app_insights_connection_string, resource=resource
    )
    enable_instrumentation()
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True
    log.info("telemetry: Application Insights on as service %s", SERVICE_NAME)
    return True
