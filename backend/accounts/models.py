from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Custom user model with role field for RBAC.

    Roles:
        ADMIN – can manage users and agents.
        AGENT – can work with tickets.
    """

    ROLE_ADMIN = 'ADMIN'
    ROLE_AGENT = 'AGENT'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_AGENT, 'Agent'),
    ]

    role = models.CharField(max_length=5, choices=ROLE_CHOICES, default=ROLE_AGENT)

    # Override default ManyToMany fields to avoid reverse accessor name clashes
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    def is_agent(self):
        return self.role == self.ROLE_AGENT
