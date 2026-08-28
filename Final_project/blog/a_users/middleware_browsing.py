"""Optional middleware — browsing history is recorded in ArticlePage.serve()."""

from a_users.models import BrowsingHistory
from a_blog.models import ArticlePage


class BrowsingHistoryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method != 'GET' or response.status_code != 200:
            return response
        if not request.user.is_authenticated:
            return response

        page = getattr(request, 'wagtail_page', None)
        if isinstance(page, ArticlePage):
            page_url = page.get_url(request) or page.url
            if page_url:
                BrowsingHistory.add_or_update_history(
                    user=request.user,
                    article_id=page.pk,
                    article_title=page.title,
                    article_url=request.build_absolute_uri(page_url),
                )

        return response
