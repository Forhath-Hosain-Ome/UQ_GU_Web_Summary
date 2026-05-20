from django.db import models
from django.contrib.auth.models import User

class BaseModel(models.Model):
    """
    Base model with common timestamp fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="%(class)s_created")

    class Meta:
        abstract = True