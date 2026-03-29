from django.views.generic.base import ContextMixin

class BaseViewMixin(ContextMixin):
    """
    Base mixin for views with common context data.
    """
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add common context here if needed
        return context