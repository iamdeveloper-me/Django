from django.contrib.gis.admin import GeoModelAdmin, OSMGeoAdmin
from django.contrib import admin
from django import forms
from django.contrib.auth.models import User
from organizations.models import *
from userprofile.models import Partner
from organizations.admin_filter import *
from cuser.current_user import get_current_user
from django.utils import timezone
import pytz

class ListStyleAdminMixin(object):
    def get_row_css(self, obj, index):
        return ''

"""Sensor Section"""

class SensorForm(forms.ModelForm):
    license_file = forms.FileField(required=False)

    class Media:
        js = ('js/jquery.min.js', 'custom-admin.js')

    def __init__(self, *args, **kwargs):
        self.check_balena_application_uuid = False
        super(SensorForm, self).__init__(*args, **kwargs)

        if 'instance' in kwargs:
            if kwargs['instance'] != None:
                if kwargs['instance'].balena_application_uuid and kwargs['instance']:
                    self.fields['balena_application_uuid'].widget.attrs['readonly'] = True
                    self.check_balena_application_uuid = True

        self.fields['license'].widget.attrs['readonly'] = True
        self.fields['api_key'].widget.attrs['readonly'] = True
        # self.fields['balena_uuid'].widget.attrs['readonly'] = True
        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            self.fields['client_uuid'].queryset = clients

    class Meta:
        model = Sensor
        exclude = ['created_at', 'modified_at']

    # def clean(self):
    #     cleaned_data = self.cleaned_data

    #     if self.check_balena_application_uuid == False:
    #         is_balena = cleaned_data['type'] == 'Balena'
    #         if is_balena:
    #             if cleaned_data["balena_application_uuid"] == None:
    #                 msg = 'This field is required.'
    #                 self._errors['balena_application_uuid'] = self.error_class([msg])
    #                 del cleaned_data['balena_application_uuid']

    #                 return cleaned_data

    #             sensor = Sensor.objects.filter(balena_application_uuid=cleaned_data["balena_application_uuid"])

    #             # Check uniqness of balena_application_uuid.
    #             if sensor.exists():
    #                 msg = 'It must be unique.'
    #                 self._errors['balena_application_uuid'] = self.error_class([msg])
    #                 del cleaned_data['balena_application_uuid']

    #     return cleaned_data

class SensorAdmin(admin.ModelAdmin, ListStyleAdminMixin):
    # change_list_template = "admin/organizations/sensor/change_list.html"
    change_list_results_template = "admin/organizations/sensor/change_list_results.html"

    list_display = ["name", "client_uuid", 'last_data_received', 'balena_uuid', 'fingerprint_file']
    exclude = ['default_firmware_uuid', 'force_update_firmware', 'force_default_firmware', 'force_reboot', 'force_shutdown', 'force_config', 'cpu_usage', 'cpu_temperature', 'ram_usage', 'firmware_version']

    list_filter = (CreatedAtListFilter, 'client_uuid',)

    def get_list_filter(self, request):
        default_list_filter = super(SensorAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (CreatedAtListFilter, ClientFilter,)
            return list_filter

    form = SensorForm

    def get_form(self, request, obj=None, **kwargs):
        form = super(SensorAdmin, self).get_form(request, obj=obj, **kwargs)
        form.request = request
        return form

    def get_queryset(self, request):
        qs = super(SensorAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))

    def save_model(self, request, obj, form, change):
        if request.FILES:
            file_data = request.FILES['license_file'].read().decode('utf-8')
            obj.license = file_data
        obj.user = request.user
        super().save_model(request, obj, form, change)

    # Reference: https://github.com/litchfield/django-liststyle
    def get_row_css(self, obj, index):
        if obj.last_data_received_warning:
            current_utc_datetime = timezone.now().astimezone(pytz.utc)
            last_data_received = obj.last_data_received

            time_difference_in_min = (current_utc_datetime - last_data_received).total_seconds() / 60.0

            # now < 1 hour
            if time_difference_in_min < 60:
                return 'green_row_text green_row_text%d' % index
            # now >= 1 hour and now < 12 hour
            elif time_difference_in_min >= 60 and time_difference_in_min < 720:
                return 'yellow_row_text yellow_row_text%d' % index
            # now >= 12 hour and now < 24 hour
            elif time_difference_in_min >= 720 and time_difference_in_min < 1440:
                return 'light_orange_row_text light_orange_row_text%d' % index
            # now >= 24 hour and now < 48 hour
            elif time_difference_in_min >= 1440 and time_difference_in_min < 2880:
                return 'dark_orange_row_text dark_orange_row_text%d' % index
            # now >= 48 hour and now < 72 hour
            elif time_difference_in_min >= 2880 and time_difference_in_min < 4320:
                return 'light_red_text light_red_text%d' % index
            # now >= 72 hour
            else:
                return 'dark_red_text dark_red_text%d' % index
        return ''

"""End Sensor Section"""


"""Store Section"""

class StoreForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(StoreForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            self.fields['client_uuid'].queryset = clients

    class Media:
        js = ('js/jquery.min.js', 'js/store_custom.js')

    class Meta:
        model = Store
        exclude = ['created_at', 'modified_at']

class StoreAdmin(OSMGeoAdmin):

    list_display = ["name", "client_uuid", "country", "state", "city"]

    list_filter = ('client_uuid', )

    def get_list_filter(self, request):
        default_list_filter = super(StoreAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (ClientFilter,)
            return list_filter

    form = StoreForm

    def get_queryset(self, request):
        qs = super(StoreAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))

"""End Store Section"""


"""Start PointOfSale Section"""

class PointOfSaleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PointOfSaleForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            clients_uuid = clients.values_list('uuid', flat=True)

            self.fields['client_uuid'].queryset = clients
            self.fields['sensor_uuid'].queryset = Sensor.objects.filter(client_uuid__in=clients_uuid)
            self.fields['store_uuid'].queryset = Store.objects.filter(client_uuid__in=clients_uuid)

    class Meta:
        PointOfSale
        exclude = ['created_at', 'modified_at']

class PointOfSaleAdmin(admin.ModelAdmin):
    # list_select_related = ( 'client_uuid', 'store_uuid',)
    list_display = ["name", "client_pos_uuid", 'store_uuid']

    list_filter = ('client_uuid',)

    def get_list_filter(self, request):
        default_list_filter = super(PointOfSaleAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (ClientFilter,)
            return list_filter

    form = PointOfSaleForm

    def get_queryset(self, request):
        qs = super(PointOfSaleAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))

"""End PointOfSale Section"""


"""Transaction & TransactionLines Section"""

class TransactionForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(TransactionForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            self.fields['client_uuid'].queryset = clients

    class Meta:
        exclude = ['created_at', 'modified_at']

class TransactionAdmin(admin.ModelAdmin):
    def fomatted_start_rec_at(self, obj):
        if obj.start_rec_at != None :
            return obj.start_rec_at.strftime("%b %d, %Y, %H:%M:%S")
    def fomatted_end_rec_at(self, obj):
        if obj.stop_rec_at != None :
            return obj.stop_rec_at.strftime("%b %d, %Y, %H:%M:%S")

    list_display = ["uuid", "fomatted_start_rec_at", "fomatted_end_rec_at", "client_uuid", "client_transaction_uuid", "customer_uuid", "client_customer_uuid", 'currency', 'currency_exchange_rate', 'in_house', 'purchased_at', 'price', 'amount', 'discount', 'vat', 'payment_type', 'age', 'gender', 'start_rec_at', 'stop_rec_at', 'duration', 'glasses', 'ethnicity', 'times_resumed', 'min_smile', 'avg_smile', 'max_smile', 'min_happiness', 'avg_happiness', 'max_happiness', 'min_surprise', 'avg_surprise', 'max_surprise', 'min_fear', 'avg_fear', 'max_fear', 'min_anger', 'avg_anger', 'max_anger', 'min_neutral', 'avg_neutral', 'max_neutral', 'avg_disgust', 'max_disgust', 'min_disgust', 'matcher_has_run', 'has_demographics', 'customer_matched', 'client_pos_uuid']

    list_filter = (CreatedAtListFilter, 'client_uuid', )

    def get_list_filter(self, request):
        default_list_filter = super(TransactionAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (CreatedAtListFilter, ClientFilter,)
            return list_filter

    form = TransactionForm

    def get_queryset(self, request):
        qs = super(TransactionAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))


class TransactionLinesForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(TransactionLinesForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user())).values_list('uuid', flat=True)
            self.fields['transaction_uuid'].queryset = Transaction.objects.filter(client_uuid__in = clients_uuid)

    class Meta:
        exclude = ['created_at', 'modified_at']

class TransactionLinesAdmin(admin.ModelAdmin):
    def fomatted_start_rec_at(self, obj):
        if obj.start_rec_at != None :
            return obj.start_rec_at.strftime("%b %d, %Y, %H:%M:%S")
    def fomatted_end_rec_at(self, obj):
        if obj.stop_rec_at != None :
            return obj.stop_rec_at.strftime("%b %d, %Y, %H:%M:%S")

    list_display = ["uuid", "fomatted_start_rec_at", "fomatted_end_rec_at", 'client_product_name', 'purchased_at', 'currency', 'currency_exchange_rate', 'price', 'amount', 'discount', 'vat', 'client_product_sku', 'client_product_category_sku', 'age', 'gender', 'start_rec_at', 'stop_rec_at', 'duration', 'glasses', 'ethnicity', 'times_resumed', 'min_smile', 'avg_smile', 'max_smile', 'min_happiness', 'avg_happiness', 'max_happiness', 'min_surprise', 'avg_surprise', 'max_surprise', 'min_fear', 'avg_fear', 'max_fear', 'min_anger', 'avg_anger', 'max_anger', 'min_neutral', 'avg_neutral', 'max_neutral', 'avg_disgust', 'max_disgust', 'min_disgust', 'matcher_has_run', 'has_demographics', 'customer_matched', 'client_pos_uuid', 'customer_uuid', 'client_transaction_uuid']

    list_filter = (CreatedAtListFilter, )

    form = TransactionLinesForm

    def get_queryset(self, request):
        qs = super(TransactionLinesAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user())).values_list('uuid', flat=True)
        return qs.filter(transaction_uuid__in = Transaction.objects.filter(client_uuid__in = clients_uuid))

"""End Transaction & TransactionLines Section"""


"""Product & ProductCategory Section"""

class ProductCategoryForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProductCategoryForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            self.fields['client_uuid'].queryset = clients

    class Meta:
        exclude = ['created_at', 'modified_at']

class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "client_product_category_sku", "client_uuid"]

    list_filter = ('client_uuid', )

    def get_list_filter(self, request):
        default_list_filter = super(ProductCategoryAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (ClientFilter,)
            return list_filter

    form = ProductCategoryForm

    def get_queryset(self, request):
        qs = super(ProductCategoryAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))


class ProductForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(ProductForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user()))
            self.fields['client_uuid'].queryset = clients

    class Meta:
        exclude = ['created_at', 'modified_at']

class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "client_uuid", "profit_per_unit", "client_product_category_sku", "client_product_sku"]

    list_filter = ('client_uuid', )

    def get_list_filter(self, request):
        default_list_filter = super(ProductAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (ClientFilter,)
            return list_filter

    form = ProductForm

    def get_queryset(self, request):
        qs = super(ProductAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))

"""End Product & ProductCategory Section"""


"""Demographic Section"""

class DemographicForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(DemographicForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user())).values_list('uuid', flat=True)
            self.fields['sensor_uuid'].queryset = Sensor.objects.filter(client_uuid__in = clients_uuid)

    class Meta:
        exclude = ['created_at', 'modified_at']

class DemographicAdmin(admin.ModelAdmin):
    def fomatted_start_rec_at(self, obj):
        return obj.start_rec_at and obj.start_rec_at.strftime("%b %d, %Y, %H:%M:%S")
    def fomatted_end_rec_at(self, obj):
        return obj.stop_rec_at and obj.stop_rec_at.strftime("%b %d, %Y, %H:%M:%S")
    def sensor_name(self, obj):
        return obj.sensor_uuid.name

    list_display = ['uuid', 'fomatted_start_rec_at', 'fomatted_end_rec_at', 'age', 'gender', 'duration', 'glasses', 'ethnicity', 'times_resumed', 'min_smile', 'avg_smile', 'max_smile', 'min_happiness', 'avg_happiness', 'max_happiness', 'min_surprise', 'avg_surprise', 'max_surprise', 'min_fear', 'avg_fear', 'max_fear', 'min_anger', 'avg_anger', 'max_anger', 'min_neutral', 'avg_neutral', 'max_neutral', 'avg_disgust', 'max_disgust', 'min_disgust', 'avg_sadness', 'min_sadness', 'max_sadness', 'face_looked_attention_time', 'face_descriptor', 'start_rec_at', 'stop_rec_at', 'created_at', 'modified_at', 'sensor_name']

    readonly_fields = ('fomatted_start_rec_at', 'fomatted_end_rec_at')

    list_filter = (CreatedAtListFilter, StoreNameDemographicFilter, ClientNameDemographicFilter, SensorNameDemographicFilter,)

    form = DemographicForm

    def get_queryset(self, request):
        qs = super(DemographicAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        clients_uuid = Client.objects.filter(partner_uuid = Partner.objects.get(user = get_current_user())).values_list('uuid', flat=True)
        return qs.filter(sensor_uuid__in = Sensor.objects.filter(client_uuid__in = clients_uuid).values_list('uuid', flat=True))

"""End Demographic Section"""


"""Weather Section"""

class WeatherForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(WeatherForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            self.fields['store_uuid'].queryset = Store.objects.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True))

    class Meta:
        exclude = ['created_at', 'modified_at']

class WeatherAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'time', 'summary', 'icon', 'precipIntensity', 'precipProbability', 'precipAccumulation', 'precipType', 'temperature', 'apparentTemperature', 'dewPoint', 'humidity', 'pressure', 'windSpeed', 'windGust', 'windBearing', 'cloudCover', 'uvIndex', 'visibility', 'ozone', '_store_uuid', 'created_at']

    list_filter = (StoreNameWeatherFilter, ClientNameWeatherFilter,)

    def _store_uuid(self, obj):
        return obj.store_uuid
    _store_uuid.short_description = 'Store Name'

    form = WeatherForm

    def get_queryset(self, request):
        qs = super(WeatherAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs

        return qs.filter(store_uuid__in=Store.objects.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user())).values_list('uuid', flat=True)).values_list('uuid', flat=True))

"""End Weather Section"""

"""Customer Section"""

class CustomerForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(CustomerForm, self).__init__(*args, **kwargs)

        if get_current_user().is_partner:
            self.fields['client_uuid'].queryset = Client.objects.filter(partner_uuid=Partner.objects.get(user=get_current_user()))

    class Meta:
        exclude = ['created_at', 'modified_at']

class CustomerAdmin(admin.ModelAdmin):
    list_display = ['uuid', '_client_uuid']

    def _client_uuid(self, obj):
        return obj.client_uuid
    _client_uuid.short_description = 'Client Name'

    list_filter = ('client_uuid', )

    def get_list_filter(self, request):
        default_list_filter = super(CustomerAdmin, self).get_list_filter(request)
        if request.user.is_superuser:
             return default_list_filter

        if request.user.is_partner:
            list_filter = (ClientFilter,)
            return list_filter

    form = CustomerForm

    def get_queryset(self, request):
        qs = super(CustomerAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(client_uuid__in=Client.objects.filter(partner_uuid=Partner.objects.get(user=request.user)))

"""End Customer Section"""

admin.site.register(Sensor, SensorAdmin)
admin.site.register(Store, StoreAdmin)
admin.site.register(PointOfSale, PointOfSaleAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(TransactionLines, TransactionLinesAdmin)
admin.site.register(Product, ProductAdmin)
admin.site.register(ProductCategory,ProductCategoryAdmin)
admin.site.register(Customer, CustomerAdmin)
admin.site.register(DemographicData, DemographicAdmin)
admin.site.register(Firmware)
admin.site.register(Log)
admin.site.register(Weather, WeatherAdmin)
