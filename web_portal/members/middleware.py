from django.middleware.gzip import GZipMiddleware


class MemberPanelCompression(GZipMiddleware):
    """Compress the member's startup payloads, including streamed CSS/JS files."""

    def process_response(self, request, response):
        if request.path in {'/dashboard', '/member.css', '/member.js', '/api/member/workspace'}:
            return super().process_response(request, response)
        return response
