class FixAuthorizationHeaderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'HTTP_AUTHORIZATION' in request.META:
            request.META['Authorization'] = request.META['HTTP_AUTHORIZATION']
        response = self.get_response(request)
        return response
