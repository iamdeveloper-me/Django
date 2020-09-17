from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from organizations.models import Store, Client, Sensor, PointOfSale, Partner
from cuser.current_user import get_current_user

class CreatedAtListFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Created At')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'created_at'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        return (
            ('newest', _('By Newest')),
            ('oldest', _('By Oldest')),
        )

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value (either 'newest' or 'oldest')
        # to decide how to filter the queryset.
        if self.value() == 'newest':
            return queryset.order_by('-created_at')
        if self.value() == 'oldest':
            return queryset.order_by('created_at')

class ClientFilter(admin.SimpleListFilter):

    title = 'Client'
    parameter_name = 'client'

    def lookups(self, request, model_admin):
        clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = request.user))
        return [(c.uuid, c.name) for c in clients]

    def queryset(self, request, queryset):
        clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = request.user)).values_list('uuid', flat=True)
        return queryset.filter(client_uuid__in = clients_uuid)


"""Weather Filter Section"""
class StoreNameWeatherFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Store Name')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'store_uuid'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_stores = []

        if request.user.is_superuser:
            queryset = Store.objects.all()
        else:
            queryset = Store.objects.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())))

        for stores in queryset:
            list_of_stores.append(
                (str(stores.uuid), stores.name)
            )
        return sorted(list_of_stores, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if request.GET.get('store_uuid'):
            
            return queryset.filter(store_uuid=request.GET.get('store_uuid'))
        return queryset
        
class ClientNameWeatherFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Client Name')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'client_uuid'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_clients = []

        if request.user.is_superuser:
            queryset = Client.objects.all()
        else:
            queryset = Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user()))

        for clients in queryset:
            list_of_clients.append(
                (str(clients.uuid), clients.name)
            )
        return sorted(list_of_clients, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if request.GET.get('client_uuid'):
            stores = Store.objects.filter(client_uuid_id=request.GET.get('client_uuid'))
            return queryset.filter(store_uuid__in=stores)
        return queryset
        
"""End Weather Filter Section"""


"""Demographic Filter Section"""

class StoreNameDemographicFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Store Name')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'store_uuid'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_stores = []

        if request.user.is_superuser:
            queryset = Store.objects.all()
        else:
            queryset = Store.objects.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())))

        for stores in queryset:
            list_of_stores.append(
                (str(stores.uuid), stores.name)
            )
        return sorted(list_of_stores, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if request.GET.get('store_uuid'):
            pos_sensors = PointOfSale.objects.filter(store_uuid = Store.objects.get(uuid=request.GET.get('store_uuid'))).values_list('sensor_uuid')
            sensors = Sensor.objects.filter(uuid__in=pos_sensors)
            
            return queryset.filter(sensor_uuid__in=sensors)
        return queryset
        
class ClientNameDemographicFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Client Name')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'client_uuid'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_clients = []

        if request.user.is_superuser:
            queryset = Client.objects.all()
        else:
            queryset = Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user()))

        for clients in queryset:
            list_of_clients.append(
                (str(clients.uuid), clients.name)
            )
        return sorted(list_of_clients, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if request.GET.get('client_uuid'):
            sensors = Sensor.objects.filter(client_uuid_id=request.GET.get('client_uuid'))
            return queryset.filter(sensor_uuid__in=sensors)
        return queryset

class SensorNameDemographicFilter(admin.SimpleListFilter):
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = _('Sensor Name')

    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'sensor_uuid'

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        list_of_sensors = []

        if request.user.is_superuser:
            queryset = Sensor.objects.all()
        else:
            clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user())).values_list('uuid', flat=True)
            queryset = Sensor.objects.filter(client_uuid__in=clients_uuid)

        for sensors in queryset:
            list_of_sensors.append(
                (str(sensors.uuid), sensors.name)
            )
        return sorted(list_of_sensors, key=lambda tp: tp[1])

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        if request.GET.get('sensor_uuid'):
            return queryset.filter(sensor_uuid=request.GET.get('sensor_uuid'))
        return queryset
        
"""End Demographic Filter Section"""
