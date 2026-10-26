"""tests/test_result_backend.py — result reads share one Celery backend across threads.

Reasoning:
- Celery keeps a separate backend per thread unless the backend class is thread-safe, and the
  Redis one is not. The result reads in api/routes/var.py run in a thread pool whose threads
  are retired after 10 idle seconds, so without a shared backend a long-lived API process built
  a new client, connection pool and TLS context (about 1 MiB) for every new pool thread and kept
  the retired threads' ones in reference cycles until the next full garbage collection. The
  numbers are in docs/plan-streaming-quotes-in-results-out.md section 9.
- Real threads, no mocking of the thing under test: what matters is that many threads get the
  same object and that it is built once.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import api.routes.var as var_routes


def _fresh():
    return patch.object(var_routes, "_result_backend", None)


def test_every_thread_gets_the_same_backend_and_it_is_built_once():
    created = []

    def build():
        backend = MagicMock()
        created.append(backend)
        return backend

    fake_app = MagicMock()
    type(fake_app).backend = property(lambda _self: build())
    seen = []
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        seen.append(var_routes._shared_result_backend())

    with _fresh(), patch.object(var_routes, "celery_app", fake_app):
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(created) == 1
    assert len(seen) == 8 and all(backend is created[0] for backend in seen)


def test_the_result_read_goes_through_the_shared_backend():
    backend = object()
    async_result = MagicMock()
    async_result.state = "PENDING"

    with (
        patch.object(var_routes, "_shared_result_backend", return_value=backend),
        patch.object(var_routes, "AsyncResult", return_value=async_result) as ctor,
    ):
        assert var_routes._read_celery_result("task-1") == ("PENDING", None, None)

    assert ctor.call_args.kwargs["backend"] is backend
