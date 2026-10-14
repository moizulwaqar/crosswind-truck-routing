"""Single-process HTTP server for the 128 MiB host.

Gunicorn keeps a master and a worker. Together they cross 128 MiB during a
forecast. This server is one process, with at most two requests in flight so a
health check can still get through while a plan is running.
"""
import os
import threading
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from config.wsgi import application

_slots = threading.Semaphore(2)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    block_on_close = False

    def process_request(self, request, client_address):
        _slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            _slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            _slots.release()


def main():
    port = int(os.environ.get("PORT", "8000"))
    httpd = make_server(
        "0.0.0.0",
        port,
        application,
        server_class=ThreadingWSGIServer,
        handler_class=QuietHandler,
    )
    print(f"Listening on 0.0.0.0:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
