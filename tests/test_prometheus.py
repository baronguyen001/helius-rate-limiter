import pytest

from helius_limiter import prometheus
from helius_limiter.prometheus import PrometheusExporter, PrometheusUnavailableError


class FakeMetric:
    def __init__(self, name, description, labelnames=(), **kwargs):
        self.name = name
        self.description = description
        self.labelnames = labelnames
        self.kwargs = kwargs
        self.increments = []
        self.values = []

    def labels(self, **labels):
        return FakeBoundMetric(self, labels)

    def inc(self, amount=1):
        self.increments.append(({}, amount))

    def set(self, value):
        self.values.append(({}, value))


class FakeBoundMetric:
    def __init__(self, metric, labels):
        self.metric = metric
        self.labels = labels

    def inc(self, amount=1):
        self.metric.increments.append((self.labels, amount))

    def set(self, value):
        self.metric.values.append((self.labels, value))


class FakePrometheusClient:
    def __init__(self):
        self.metrics = {}
        self.started = []

    def Counter(self, name, description, labelnames=(), **kwargs):
        metric = FakeMetric(name, description, labelnames, **kwargs)
        self.metrics[name] = metric
        return metric

    def Gauge(self, name, description, labelnames=(), **kwargs):
        metric = FakeMetric(name, description, labelnames, **kwargs)
        self.metrics[name] = metric
        return metric

    def start_http_server(self, port, *, addr="", **kwargs):
        self.started.append((port, addr, kwargs))


def test_prometheus_exporter_records_known_events(monkeypatch):
    fake_client = FakePrometheusClient()
    monkeypatch.setattr(prometheus.importlib, "import_module", lambda name: fake_client)
    monkeypatch.setattr(prometheus.time, "time", lambda: 123.0)

    exporter = PrometheusExporter(namespace="test_helius", registry="registry")
    exporter.on_event("tripped")
    exporter.on_event("reset")
    exporter.on_event("rotated")

    events_total = fake_client.metrics["test_helius_events_total"]
    circuit_open = fake_client.metrics["test_helius_circuit_open"]
    last_event = fake_client.metrics["test_helius_last_event_timestamp_seconds"]

    assert events_total.increments == [
        ({"event": "tripped"}, 1),
        ({"event": "reset"}, 1),
        ({"event": "rotated"}, 1),
    ]
    assert circuit_open.values == [({}, 1), ({}, 0)]
    assert last_event.values == [
        ({"event": "tripped"}, 123.0),
        ({"event": "reset"}, 123.0),
        ({"event": "rotated"}, 123.0),
    ]


def test_prometheus_exporter_can_start_http_server(monkeypatch):
    fake_client = FakePrometheusClient()
    monkeypatch.setattr(prometheus.importlib, "import_module", lambda name: fake_client)

    exporter = PrometheusExporter(registry="registry")
    exporter.start_http_server(9100, addr="127.0.0.1")

    assert fake_client.started == [(9100, "127.0.0.1", {"registry": "registry"})]


def test_prometheus_exporter_has_clear_error_without_client(monkeypatch):
    def missing_client(name):
        raise ImportError(name)

    monkeypatch.setattr(prometheus.importlib, "import_module", missing_client)

    with pytest.raises(PrometheusUnavailableError, match="helius-rate-limiter\\[prometheus\\]"):
        PrometheusExporter()
