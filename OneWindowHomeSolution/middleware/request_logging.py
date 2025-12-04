import logging
import time

class RequestLoggingMiddleware:
    """
    Middleware to log every request and response with timing and status code.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("django.request")

    def __call__(self, request):
        start = time.time()
        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            duration = time.time() - start
            self.logger.info(
                f"%s %s %s %s %.3fs", 
                request.method, 
                request.get_full_path(),
                response.status_code if response else 'ERR',
                getattr(request, 'user', None),
                duration
            )
