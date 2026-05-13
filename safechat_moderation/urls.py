from django.urls import path
from django.urls.resolvers import URLPattern, URLResolver

from .views import flagged_messages_panel, review_flagged_message

i18n_urlpatterns: list[URLPattern | URLResolver] = [
    path("moderation/", flagged_messages_panel, name="moderation_panel"),
    path("moderation/review/<int:flag_id>/", review_flagged_message, name="moderation_review"),
]

urlpatterns = i18n_urlpatterns
