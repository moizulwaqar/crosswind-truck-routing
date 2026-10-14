"""Give freed heap back to the OS after each request.

glibc keeps spare pages, and a 128 MiB host counts them. Trimming after a
forecast lets the next request start from the real usage instead of the peak.
"""
import ctypes


class MallocTrimMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            self._trim = ctypes.CDLL("libc.so.6").malloc_trim
        except OSError:
            self._trim = None

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            if self._trim is not None:
                self._trim(0)
