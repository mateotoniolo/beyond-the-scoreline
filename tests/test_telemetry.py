import sys

import bts.telemetry as telemetry
from bts.config import Settings
from bts.telemetry import SERVICE_NAME, configure_telemetry


def test_telemetry_noop_without_connection_string(monkeypatch):
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delitem(sys.modules, "azure.monitor.opentelemetry", raising=False)
    assert configure_telemetry(Settings(_env_file=None)) is False
    assert "azure.monitor.opentelemetry" not in sys.modules


def test_telemetry_configures_when_set(monkeypatch):
    import agent_framework.observability as observability
    import azure.monitor.opentelemetry as azure_monitor

    calls: dict = {}
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(azure_monitor, "configure_azure_monitor", lambda **kw: calls.update(kw))
    monkeypatch.setattr(
        observability, "enable_instrumentation", lambda **kw: calls.update(instrumented=True)
    )
    settings = Settings(_env_file=None, app_insights_connection_string="InstrumentationKey=abc")
    assert configure_telemetry(settings) is True
    assert calls["connection_string"] == "InstrumentationKey=abc"
    assert calls["instrumented"] is True
    assert calls["resource"].attributes["service.name"] == SERVICE_NAME
