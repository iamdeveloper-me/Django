from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    name = 'organizations'
    verbose_name = 'Partners'

    def ready(self):
        import organizations.signals  