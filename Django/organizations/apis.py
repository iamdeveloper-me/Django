from userprofile.rest_framework_import import *
from datetime import timedelta
from organizations.models import Sensor, DemographicData, Firmware
from organizations.serializers import *
from datetime import datetime, timedelta, time
from django.utils import timezone
import json, uuid, pytz
from django.core.files.base import ContentFile
from pytz import timezone

@api_view(['POST'])
@permission_classes((AllowAny,))
def demographic_create(request):
    """
        Description :
        ----------
            Create DemographicData

        Header :
        ----------
            Content-Type    : application/x-www-form-urlencoded
            api-key         : sensor_api_key        (Must in Case-2 Request URL OR body_paratemer without 'api_key')

        Request Method :
        ----------
            POST

        Request URL :
        ----------
            Case-1 : /api/v1/demographic/create/?api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/demographic/create/

        Request Parameters : (key-value pairs)
        ----------
            "api_key" : "sensor_api_key",           // Required (in case of Header OR Request URL has no 'sensor_api_key', otherwise Optional.)
            "json_data" : [
                {
                    "age" : "30",
                    "gender" : "1",
                    "duration" : "10",
                    "start_rec_at" : "1542009249282",
                    "stop_rec_at" : "1542009249282",
                    "glasses" : "0",
                    "ethnicity" : "0",
                    "times_resumed" : "20",
                    "min_smile" : "10",
                    "avg_smile" : "15",
                    "max_smile" : "30",
                    "min_happiness" : "10",
                    "avg_happiness" : "15",
                    "max_happiness" : "40",
                    "min_surprise" : "10",
                    "avg_surprise" : "5",
                    "max_surprise" : "12",
                    "min_fear" : "3",
                    "avg_fear" : "1",
                    "max_fear" : "1",
                    "min_anger" : "5",
                    "avg_anger" : "4",
                    "max_anger" : "5",
                    "min_neutral" : "7",
                    "avg_neutral" : "4",
                    "max_neutral" : "9",
                    "avg_disgust" : "0",
                    "max_disgust" : "2",
                    "min_disgust" : "1",
                    "avg_sadness" : "10",
                    "min_sadness" : "5",
                    "max_sadness" : "20",
                    "face_looked_attention_time" : "6",
                    "face_descriptor" : "ZHAFs",
                    "start_rec_at" : "1540467279",
                    "stop_rec_at" : "1540467279",
                }
            ]

        Response :
        ----------
            {
                "success": "true"
            }

        Success Response Code :
        ----------
            201

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header Or Body)
        ----------
    """
    try:
        api_key = fetch_api_key_with_body_param(request)
        json_data = json.loads(request.data['json_data'])

        if json_data:
            for dg_data in json_data:
                dg_data['sensor_uuid'] = Sensor.objects.get(api_key = api_key).uuid

                if 'start_rec_at' in dg_data:
                    dg_data['start_rec_at'] = datetime.utcfromtimestamp(int(dg_data['start_rec_at']))

                if 'stop_rec_at' in dg_data:
                    dg_data['stop_rec_at'] = datetime.utcfromtimestamp(int(dg_data['stop_rec_at']))

                serializer = DemographicDataSerializer(data=dg_data)

                if serializer.is_valid():
                    serializer.save()
            return Response({"success": "true"}, status = status.HTTP_201_CREATED)
        return Response({'message':'Json data should not be empty !'}, status = status.HTTP_400_BAD_REQUEST)

    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def sensor_demographics(request):
    """
        Description :
        ----------
            Gets List of DemographicData
        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key        (Must in Case-2 Request URL)
            from            : 20.11.2018 20:42          (Optional parameter)
            to              : 21.11.2018 20:42          (Optional parameter)
            timezone        : "Europe/Berlin"           (Optional parameter, works only if 'from' & 'to' dates are present)
            sensors          : ["uuid1", "uuid1", ..]    (Optional parameter)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/sensor_demographics/?api_key=<client_api_key>

            *** OR ***

            Case-2 : /api/v1/sensor_demographics/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            List of DemographicData in JSON format

        Success Response Code :
        ----------
            201

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """

    try:
        api_key = fetch_api_key_for_get_request(request)
        client = Client.objects.get(client_api_key = api_key)
        sensors = request.query_params.getlist("sensors")
        sensors = Sensor.objects.filter(uuid__in = sensors, client_uuid=client)
        if sensors.count() != 0:
            demographic_data = DemographicData.objects.filter(sensor_uuid__in = sensors)
        else:
            sensors = Sensor.objects.filter(client_uuid = client)
            demographic_data = DemographicData.objects.filter(sensor_uuid__in = sensors)

        if set(['from', 'to']).issubset(set(request.query_params.keys())):
            print("found from date & to date filters")
            fmt = "%d.%m.%Y %H:%M"
            t_zone = request.query_params.get('timezone')

            start_rec_at = request.query_params.get('from')
            stop_rec_at = request.query_params.get('to')

            if t_zone:
                time_zone = pytz.timezone(request.query_params.get('timezone'))

                start_rec_at = time_zone.localize(datetime.strptime(start_rec_at, fmt))

                start_rec_at_utc = start_rec_at.astimezone(pytz.utc)

                stop_rec_at = time_zone.localize(datetime.strptime(stop_rec_at, fmt))

                stop_rec_at_utc = stop_rec_at.astimezone(pytz.utc)
            else:
                # Default taking UTC timezone
                start_rec_at_utc = datetime.strptime(start_rec_at, fmt).astimezone(pytz.utc)

                stop_rec_at_utc = datetime.strptime(stop_rec_at, fmt).astimezone(pytz.utc)

            demographic_data = demographic_data.filter(start_rec_at__gte = start_rec_at_utc, stop_rec_at__lte = stop_rec_at_utc)
        else:
            print("No from date & to date filters are found.")
        
        serializer = DemographicDataSerializer(demographic_data, many = True)
        return Response(serializer.data, status = status.HTTP_200_OK)

    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes((AllowAny,))
def check_sensor_api_key(request):
    """
        Description :
        ----------sensors
            Checks Sensor is present OR not.
        Header :
        ----------
            Content-Type    : application/json
            api-key         : sensor_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/valid_sensor_api_key/?api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/valid_sensor_api_key/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            {
                "valid": true
            }

            *** OR ***

            {
                "valid": false
            }

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """

    try:
        api_key = fetch_api_key_for_get_request(request)
        sensor_data = Sensor.objects.filter(api_key = api_key)

        if sensor_data:
            return Response({'valid' : True}, status = status.HTTP_200_OK)
        return Response({'valid' : False}, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes((AllowAny,))
def create_sensor_status(request):
    """
        Description :
        ----------
            Updates Sensor Status.

        Header :
        ----------
            Content-Type    : application/x-www-form-urlencoded
            api-key         : sensor_api_key        (Must in Case-2 Request URL OR body_paratemer without 'api_key')

        Request Method :
        ----------
            POST

        Request URL :
        ----------
            Case-1 : /api/v1/sensor/status/?api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/sensor/status/

        Request Parameters : (key-value pairs)
        ----------
            "api_key" : "sensor_api_key",           // Required (in case of Header OR Request URL has no 'sensor_api_key', otherwise Optional.)
            "json_data" : {
                "cpu_usage" : "6.554",
                "cpu_temperature" : "8.560",
                "ram_usage" : "0.520",
                "firmware_version" : "1.125",       // required, default=1.00
             }

        Response :
        ----------
            {
                "uuid": "2789dee8-10e2-4ad9-baa3-cb42d84414fd",
                "name": "Sensor3",
                "api_key": "2789dee8-10e2-4ad9-1234-cb42d84414fd",
                "type": "Ubuntu",
                "balena_uuid": null,
                "fingerprint": "fingerprint",
                "license": "",
                "last_demographics_received_at": "2018-11-14T12:38:04.242494Z",
                "last_online_at": "2018-11-14T12:38:04.242499Z",
                "cpu_usage": 6.554,
                "cpu_temperature": 8.56,
                "ram_usage": 0.52,
                "firmware_version": 1.125,
                "sensor_type": null,
                "default_firmware_uuid": null,
                "force_update_firmware": false,
                "force_default_firmware": false,
                "force_reboot": false,
                "force_shutdown": false,
                "force_config": false,
                "config_text": "config text"
            }

        Success Response Code :
        ----------
            202

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header Or Body)
        ----------
    """
    try:
        api_key = fetch_api_key_with_body_param(request)

        if 'json_data' in request.data :
            data = json.loads(request.data['json_data'])
        else:
            data = request.data

        serializer = SensorStatusSerializer(instance=Sensor.objects.get(api_key = api_key), data = data)

        if serializer.is_valid(raise_exception = True):
            serializer.save()
            return Response(serializer.data, status = status.HTTP_202_ACCEPTED)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def retrieve_sensor_firmware(request):
    """
        Description :
        ----------
            Gets Details of firmware file of Sensor
        Header :
        ----------
            Content-Type    : application/json
            api-key         : sensor_api_key        (Must in Case-2 & Case-3 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/sensor/firmware/?api_key=<sensor_api_key>&firmware_uuid=234234

            *** OR ***

            Case-2 : /api/v1/sensor/firmware/

            *** OR ***

            Case-3 : /api/v1/sensor/firmware/?firmware_uuid=<firmware_uuid>

        Request Parameters :
        ----------
            -

        Response :
        ----------
            {
                "firmware_file": "/media/Documents/client_1.png"
            }

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """
 
    try:
        if 'firmware_uuid' in request.query_params :
            firmware_data = Firmware.objects.get(uuid = request.query_params.get('firmware_uuid'))
        else:
            api_key = fetch_api_key_for_get_request(request)
            sensor_data = Sensor.objects.get(api_key = api_key)
            firmware_data = sensor_data.default_firmware_uuid
        
        serializer = GetFirmwareFileSerializer(firmware_data)
        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)
    
@api_view(['POST'])
@permission_classes((AllowAny,))
def fingerprint_create(request):
    # TODO: "c2v_text" : "fingerprint11111" can be also into query params
    """
        Description :
        ----------
            Updates Sensor Fingerprint.

        Header :
        ----------
            Content-Type    : application/x-www-form-urlencoded
            api-key         : sensor_api_key        (Must in Case-2 Request URL OR body_paratemer without 'api_key')
            c2v_text        : sensor_api_key        Optional

        Request Method :
        ----------
            POST

        Request URL :
        ----------
            Case-1 : /api/v1/fingerprint/?/api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/fingerprint/

        Request Parameters : (key-value pairs)
        ----------
            "api_key" : "sensor_api_key",           // Required (in case of Header OR Request URL has no 'sensor_api_key', otherwise Optional.)
            "c2v_text" : "fingerprint11111"

        Response :
        ----------
            {
                "uuid": "9e1b9159-519f-491e-8a2b-cd93ee228283",
                "fingerprint": "fingerprint222sssssssssss22",
                "fingerprint_file": "/media/FingerprintFiles/fingerprint-8e885bcc.c2v"
            }

        Success Response Code :
        ----------
            202

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header Or Body)
        ----------
    """
    try:
        data = {}
        api_key = fetch_api_key_with_body_param(request)

        if 'c2v_text' in request.data :
            #This is for x-www content type
            data['fingerprint'] = request.data['c2v_text']
        else:
            #This is for query params
            data['fingerprint'] = request.query_params.get('c2v_text')

        serializer = SensorFingerprintSerializer(instance = Sensor.objects.get(api_key = api_key), data = data)
        serializer.is_valid(raise_exception = True)
        
        # TODO: Instead of saving twice, save in signle shot.
        obj = serializer.save()
        file_name = "fingerprint-" + str(uuid.uuid4())[:8] + ".c2v"
        obj.fingerprint_file.save(file_name, ContentFile(data['fingerprint']))

        return Response(serializer.data, status = status.HTTP_202_ACCEPTED)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def license_retrieve(request, uuid=None):
    """
        Description :
        ----------
            Gets Details of license of Sensor

        Header :
        ----------
            Content-Type    : application/json
            api-key         : sensor_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/license/?api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/license/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            {
                "license": "<?xml version=\"1.0\" encoding=\"UTF-8\" ?>  <hasp_info>  <host_fingerprint type=\"SL-AdminMode\" crc=\"1991331503\">MXhJSUVEOSgRKooCWBuB3alkgIAbMgNgLQiLUFLO2hcaAiAuCBDxrgKCBJQKwKMJ7m7EnRTB4hGGlEuISCkV5WaaNwAvAZOqUFbMViZKAFkkXlXy5lyFcjMAssZAqm7EuiLwhgM6BQfM</host_fingerprint>  <host_fingerprint type=\"SL-UserMode\" vendorid=\"111186\" crc=\"2789293454\">MnhJScXdCHdFAM0DdKU2ArsR5axEKC0YYIG1ICxKJSsE3JgBgFRxQYAIJUWsfYlhALg9muBu3lVAkEDSAdCScgkRG3EpRTB7gKHBS8CkopS+cjPPAYDgLBKvqlA2zFY6SgBsssZAquQNugoVJgCQdAoOmA==</host_fingerprint> </hasp_info>"
            }

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """

    try:
        api_key = fetch_api_key_for_get_request(request)
        sensor_data = Sensor.objects.get(api_key = api_key)
        serializer = GetSensorLincenseSerializer(sensor_data)

        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def get_sensor_config_text(request):
    """
        Description :
        ----------
            Gets Details of config_text of Sensor

        Header :
        ----------
            Content-Type    : application/json
            api-key         : sensor_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/sensor/config/?api_key=<sensor_api_key>

            *** OR ***

            Case-2 : /api/v1/sensor/config/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            {
                "config_text": "Text of Config Text Attribute."
            }

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """

    try:
        api_key = fetch_api_key_for_get_request(request)
        sensor_data = Sensor.objects.get(api_key = api_key)
        serializer = GetSensorConfigTextSerializer(sensor_data)

        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

class TransactionApiView(APIView):
    txn_serializer_class = TransactionSerializer
    txn_line_serializer_class = TransactionLinesSerializer

    permission_classes = (AllowAny,)

    def post(self, request):
        """
            Description :
            ----------
                Create Transaction
            Header :
            ----------
                Content-Type    : application/x-www-form-urlencoded
                api-key         : client_api_key        (Must in Case-2 Request URL OR body_paratemer without 'api_key')

            Request Method :
            ----------
                POST

            Request URL :
            ----------
                Case-1 : api/v1/transactions/?api_key=<client_api_key>

                *** OR ***

                Case-2 : api/v1/transactions/

            Request Parameters : (key-value pairs)
            ----------
                "api_key" : "client_api_key",           // Required (in case of Header OR Request URL has no 'client_api_key', otherwise Optional.)
                "json_data" : {
                    "client_transaction_uuid": "Client transaction uuid",   // Required
                    "client_pos_uuid": "clt pos uid",                       // Required
                    "purchased_at":  "10-04-2018 19:55:45",
                    "in_house":  "to go",
                    "payment_type": "Cash",
                    "currency":  "EUR",
                    "currency_exchange_rate":  "1.453",
                    "purchased_at":  "10-04-2018 19:55:45",
                    "price":  10.50,
                    "amount":  2.5,
                    "discount":  4.5,
                    "vat":  1.54,
                    "meta":  [{"comment": "super discount friday", "another_field": "test"}],
                    "transaction_lines": [
                        {
                            "price": 2.4,
                            "amount": 1.0,
                            "discount": 0.5,
                            "client_product_sku": "Cocal Cola 0.2l",
                            "client_product_category_sku": "soft drinks",
                            "meta": [{"color": "red"}]
                        },
                        {
                            "price": 3.2,
                            "amount": 2.0,
                            "discount": 0.0,
                            "client_product_sku": "Chicken Wings",
                            "client_product_category_sku": "food"
                        }
                    ]
                }

            Response :
            ----------
                {
                    "uuid": "76bee18c-69a8-494c-8a41-dbae70ecebbb",
                    "in_house": "to go",
                    "payment_type": "Cash",
                    "currency": "EUR",
                    "currency_exchange_rate": 1.453,
                    "purchased_at": "2018-04-10T19:55:45Z",
                    "price": 10.5,
                    "amount": 2.5,
                    "discount": 4.5,
                    "vat": 1.54,
                    "age": null,
                    "gender": null,
                    "start_rec_at": null,
                    "stop_rec_at": null,
                    "duration": null,
                    "glasses": null,
                    "ethnicity": null,
                    "times_resumed": null,
                    "min_smile": null,
                    "avg_smile": null,
                    "max_smile": null,
                    "min_happiness": null,
                    "avg_happiness": null,
                    "max_happiness": null,
                    "min_surprise": null,
                    "avg_surprise": null,
                    "max_surprise": null,
                    "min_fear": null,
                    "avg_fear": null,
                    "max_fear": null,
                    "min_anger": null,
                    "avg_anger": null,
                    "max_anger": null,
                    "min_neutral": null,
                    "avg_neutral": null,
                    "max_neutral": null,
                    "avg_disgust": null,
                    "max_disgust": null,
                    "min_disgust": null,
                    "matcher_has_run": false,
                    "has_demographics": false,
                    "customer_matched": false,
                    "meta": [
                        {
                            "comment": "super discount friday",
                            "another_field": "test"
                        }
                    ],
                    "weather_time": null,
                    "weather_summary": null,
                    "weather_icon": null,
                    "weather_precipIntensity": null,
                    "weather_precipProbability": null,
                    "precipAccumulation": null,
                    "precipType": null,
                    "weather_temperature": null,
                    "weather_apparentTemperature": null,
                    "weather_dewPoint": null,
                    "weather_humidity": null,
                    "weather_pressure": null,
                    "weather_windSpeed": null,
                    "windGust": null,
                    "weather_windBearing": null,
                    "weather_cloudCover": null,
                    "weather_uvIndex": null,
                    "weather_visibility": null,
                    "ozone": null,
                    "client_pos_uuid": "clt pos uid",
                    "face_descriptor": null,
                    "client_customer_uuid": null,
                    "customer_uuid": null,
                    "client_transaction_uuid": "d9144e3b-4363-4db9-bd63-41608577be39",
                    "client_uuid": "96801b45-8aaa-4779-82a4-7a705b7ad591",
                    "transaction_lines": [
                        {
                            "uuid": "1d354a69-bb00-4db1-8dde-8dd27b7362bf",
                            "currency": "EUR",
                            "currency_exchange_rate": null,
                            "purchased_at": null,
                            "price": 2.4,
                            "amount": 1,
                            "discount": 0.5,
                            "vat": null,
                            "age": null,
                            "gender": null,
                            "start_rec_at": null,
                            "stop_rec_at": null,
                            "duration": null,
                            "glasses": null,
                            "ethnicity": null,
                            "times_resumed": null,
                            "min_smile": null,
                            "avg_smile": null,
                            "max_smile": null,
                            "min_happiness": null,
                            "avg_happiness": null,
                            "max_happiness": null,
                            "min_surprise": null,
                            "avg_surprise": null,
                            "max_surprise": null,
                            "min_fear": null,
                            "avg_fear": null,
                            "max_fear": null,
                            "min_anger": null,
                            "avg_anger": null,
                            "max_anger": null,
                            "min_neutral": null,
                            "avg_neutral": null,
                            "max_neutral": null,
                            "avg_disgust": null,
                            "max_disgust": null,
                            "min_disgust": null,
                            "matcher_has_run": false,
                            "has_demographics": false,
                            "customer_matched": false,
                            "meta": [
                                {
                                    "color": "red"
                                }
                            ],
                            "weather_time": null,
                            "weather_summary": null,
                            "weather_icon": null,
                            "weather_precipIntensity": null,
                            "weather_precipProbability": null,
                            "precipAccumulation": null,
                            "precipType": null,
                            "weather_temperature": null,
                            "weather_apparentTemperature": null,
                            "weather_dewPoint": null,
                            "weather_humidity": null,
                            "weather_pressure": null,
                            "weather_windSpeed": null,
                            "windGust": null,
                            "weather_windBearing": null,
                            "weather_cloudCover": null,
                            "weather_uvIndex": null,
                            "weather_visibility": null,
                            "ozone": null,
                            "client_product_name": null,
                            "client_product_sku": "Cocal Cola 0.2l",
                            "client_product_category_sku": "soft drinks",
                            "client_transaction_uuid": "clt pos uid",
                            "client_pos_uuid": "clt pos uid",
                            "customer_uuid": null,
                            "transaction_uuid": "76bee18c-69a8-494c-8a41-dbae70ecebbb"
                        }
                    ]
                }

            Success Response Code :
            ----------
                201

            Error Response Code :
            ----------
                400

            Note: API Key is must (Either in Query Params OR Header Or Body)
            ----------
        """
        try:
            txn_lines_resp_data = []
            api_key = fetch_api_key_with_body_param(request)

            if 'json_data' in request.data :
                data = json.loads(request.data['json_data'])
            else:
                data = request.data

            # Pops out Transaction Lines json data from request
            is_txn_lines = 'transaction_lines' in data
            if is_txn_lines:
                transaction_lines_data = data.pop('transaction_lines')

            client_uuid = Client.objects.get(client_api_key = api_key).uuid
            data['client_uuid'] = client_uuid

            is_purchased_at = 'purchased_at' in data
            if is_purchased_at:
                data['purchased_at'] = datetime.strptime(data['purchased_at'], '%d-%m-%Y %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')

            # Create Transaction
            txn_serializer = self.txn_serializer_class(data = data)
            txn_serializer.is_valid(raise_exception = True)
            txn_serializer.save()

            # Create TransactionLines
            if is_txn_lines and transaction_lines_data:
                for txn_line_data in transaction_lines_data:
                    txn_line_data['transaction_uuid'] = txn_serializer.data['uuid']
                    txn_line_data['client_transaction_uuid'] = txn_serializer.data['client_transaction_uuid']
                    txn_line_data['client_pos_uuid'] = txn_serializer.data['client_pos_uuid']

                    txn_line_serializer = self.txn_line_serializer_class(data = txn_line_data)

                    if txn_line_serializer.is_valid():
                        txn_line_serializer.save()
                        txn_lines_resp_data.append(txn_line_serializer.data)

            response_data = txn_serializer.data
            response_data['transaction_lines'] = txn_lines_resp_data
            return Response(response_data, status = status.HTTP_201_CREATED)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        """
            Description :
            ----------
                Get Details of Transaction

            Header :
            ----------
                Content-Type                : application/json
                api-key                     : client_api_key                        (Must in Case-2 Request URL)
                client_transaction_uuid     : 9040e4f2-05cd-46da-8f02-d19ec78a1e93  (Must)

            Request Method :
            ----------
                GET

            Request URL :
            ----------
                Case-1 : /api/v1/transaction/?api_key=<client_api_key>

                *** OR ***

                Case-2 : /api/v1/transaction/

            Request Parameters :
            ----------
                -

            Response :
            ----------
                {
                    "uuid": "48c5cb3f-61fd-4628-aab7-32e84688d2a6",
                    "in_house": null,
                    "payment_type": "Cash",
                    "currency": "EUR",
                    "currency_exchange_rate": 12,
                    "purchased_at": "2018-11-27T10:37:39Z",
                    "price": null,
                    "amount": null,
                    "discount": null,
                    "vat": null,
                    "age": null,
                    "gender": null,
                    "start_rec_at": null,
                    "stop_rec_at": null,
                    "duration": null,
                    "glasses": null,
                    "ethnicity": null,
                    "times_resumed": null,
                    "min_smile": null,
                    "avg_smile": null,
                    "max_smile": null,
                    "min_happiness": null,
                    "avg_happiness": null,
                    "max_happiness": null,
                    "min_surprise": null,
                    "avg_surprise": null,
                    "max_surprise": null,
                    "min_fear": null,
                    "avg_fear": null,
                    "max_fear": null,
                    "min_anger": null,
                    "avg_anger": null,
                    "max_anger": null,
                    "min_neutral": null,
                    "avg_neutral": null,
                    "max_neutral": null,
                    "avg_disgust": null,
                    "max_disgust": null,
                    "min_disgust": null,
                    "matcher_has_run": false,
                    "has_demographics": false,
                    "customer_matched": false,
                    "meta": null,
                    "weather_time": null,
                    "weather_summary": null,
                    "weather_icon": null,
                    "weather_precipIntensity": null,
                    "weather_precipProbability": null,
                    "precipAccumulation": null,
                    "precipType": null,
                    "weather_temperature": null,
                    "weather_apparentTemperature": null,
                    "weather_dewPoint": null,
                    "weather_humidity": null,
                    "weather_pressure": null,
                    "weather_windSpeed": null,
                    "windGust": null,
                    "weather_windBearing": null,
                    "weather_cloudCover": null,
                    "weather_uvIndex": null,
                    "weather_visibility": null,
                    "ozone": null,
                    "client_pos_uuid": "Client pos uuid",
                    "face_descriptor": "Face descriptor",
                    "client_customer_uuid": null,
                    "customer_uuid": null,
                    "client_transaction_uuid": "9040e4f2-05cd-46da-8f02-d19ec78a1e93",
                    "client_uuid": "e53f7385-f660-49ad-9b48-b660af001e96"
                }

            Success Response Code :
            ----------
                200

            Error Response Code :
            ----------
                400
        """

        try:
            client_uuid = find_client_uuid(request)
            txn = Transaction.objects.get(client_transaction_uuid = request.query_params.get('client_transaction_uuid'), client_uuid = client_uuid)

            serializer = TransactionSerializer(txn)
            return Response(serializer.data, status = status.HTTP_200_OK)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def fetch_transactions(request):
    """
        Description :
        ----------
            Get Details of Transactions

        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key            (Must in Case-2 Request URL)
            has_demographic : 1 (true) OR 0 (false)     (Optional parameter)
            from            : 20.11.2018 20:42          (Optional parameter)
            to              : 21.11.2018 20:42          (Optional parameter)
            timezone        : "Europe/Berlin"           (Optional parameter, works only if 'from' & 'to' dates are present)
            stores          : ["uuid1", "uuid1", ..]    (Optional parameter)
            extended        : 1 (true) OR 0 (false)     (Optional parameter to fetch store_name & region_name also)
            meta_flat       : 1                         (Optional parameter for flatten meta tags.)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/transactions?api_key=<client_api_key>

            *** OR ***

            Case-2 : /api/v1/transactions
        Request Parameters :
        ----------
            -

        Response :
        ----------
            List of Transaction in JSON format

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400
    """

    try:
        meta_flat = request.query_params.get('meta_flat')
        stores = request.query_params.getlist("stores")
        has_demographic = request.query_params.get("has_demographic")
        extended = request.query_params.get("extended")

        client_uuid = find_client_uuid(request)
        txns = None
        has_no_filter = True

        # Filter 1
        if has_demographic == "1":
            has_no_filter = False
            txns = Transaction.objects.filter(client_uuid = client_uuid, has_demographics = True)
        elif has_demographic == "0":
            has_no_filter = False
            txns = Transaction.objects.filter(client_uuid = client_uuid, has_demographics = False)
        else:
            print("No has_demographic filter found.")

        # Filter 2
        if stores:
            has_no_filter = False
            if not txns:
                txns = Transaction.objects.filter(client_uuid = client_uuid)

            stores = Store.objects.filter(uuid__in = stores, client_uuid = client_uuid)
            pos = PointOfSale.objects.filter(store_uuid__in = stores).values_list('client_pos_uuid', flat=True)

            txns = txns.filter(client_pos_uuid__in = pos)
        else:
            print("No stores filter found.")

        # Filter 3
        if set(['from', 'to']).issubset(set(request.query_params.keys())):
            has_no_filter = False
            fmt = "%d.%m.%Y %H:%M"
            t_zone = request.query_params.get('timezone')

            created_at_from = request.query_params.get('from')
            created_at_to = request.query_params.get('to')

            if t_zone:
                time_zone = pytz.timezone(request.query_params.get('timezone'))

                created_at_from = time_zone.localize(datetime.strptime(created_at_from, fmt))

                created_at_from_utc = created_at_from.astimezone(pytz.utc)

                created_at_to = time_zone.localize(datetime.strptime(created_at_to, fmt))

                created_at_to_utc = created_at_to.astimezone(pytz.utc)
            else:
                # Default taking UTC timezone
                created_at_from_utc = datetime.strptime(created_at_from, fmt).astimezone(pytz.utc)

                created_at_to_utc = datetime.strptime(created_at_to, fmt).astimezone(pytz.utc)

            if not txns:
                txns = Transaction.objects.filter(created_at__gte = created_at_from_utc, created_at__lte = created_at_to_utc, client_uuid = client_uuid)
            else:
                txns = txns.filter(created_at__gte = created_at_from_utc, created_at__lte = created_at_to_utc)
        else:
            print("No from date & to date filters are found.")

        # Check if Trasaction queryset is present or not (in case of "No filters")
        if has_no_filter and not txns:
            txns = Transaction.objects.filter(client_uuid = client_uuid)

        if extended == "1":
            serializer = ExtendedTransactionSerializer(txns, many = True)
        else:
            serializer = TransactionSerializer(txns, many = True)

        if meta_flat == '1':
            response_data = process_serializer_data(serializer.data)
        else:
            response_data = serializer.data

        return Response(response_data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def fetch_transaction_line(request):
    """
        Description :
        ----------
            Get List of TransactionLines according to client_transaction_uuid query parameter

        Header :
        ----------
            Content-Type                : application/json
            api-key                     : client_api_key                        (Must in Case-2 Request URL)
            client_transaction_uuid     : 9040e4f2-05cd-46da-8f02-d19ec78a1e93  (Must)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : api/v1/transaction_line/?api_key=<client_api_key>

            *** OR ***

            Case-2 : api/v1/transaction_line/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            List of TransactionLines in JSON format

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400
    """

    try:
        client_transaction_uuid = request.query_params.get('client_transaction_uuid')
        client_uuid = find_client_uuid(request)
        txns = Transaction.objects.filter(client_uuid = client_uuid)

        txn_lines = TransactionLines.objects.filter(transaction_uuid__in = txns, client_transaction_uuid = client_transaction_uuid)

        serializer = TransactionLinesSerializer(txn_lines, many = True)
        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def fetch_transaction_lines(request):
    """
        Description :
        ----------
            Get List of TransactionLines

        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key            (Must in Case-2 Request URL)
            has_demographic : 1 (true) OR 0 (false)     (Optional parameter)
            from            : 20.11.2018 20:42          (Optional parameter)
            to              : 21.11.2018 20:42          (Optional parameter)
            timezone        : "Europe/Berlin"           (Optional parameter, works only if 'from' & 'to' dates are present)
            stores          : ["uuid1", "uuid1", ..]    (Optional parameter)
            extended        : 1 (true) OR 0 (false)     (Optional parameter to fetch store_name & region_name also)
            meta_flat       : 1                         (Optional parameter for flatten meta tags.)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : api/v1/transaction_lines/?api_key=<client_api_key>

            *** OR ***

            Case-2 : api/v1/transaction_lines/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            List of TransactionLines in JSON format

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400
    """

    try:
        meta_flat = request.query_params.get('meta_flat')
        stores = request.query_params.getlist("stores")
        has_demographic = request.query_params.get("has_demographic")
        extended = request.query_params.get("extended")

        client_uuid = find_client_uuid(request)

        # Filter 1
        if stores:
            stores = Store.objects.filter(uuid__in = stores, client_uuid = client_uuid)
            pos = PointOfSale.objects.filter(store_uuid__in = stores).values_list('client_pos_uuid', flat=True)

            txns = Transaction.objects.filter(client_uuid = client_uuid, client_pos_uuid__in = pos)
        else:
            txns = Transaction.objects.filter(client_uuid = client_uuid)
            print("No stores filter found.")
        
        txn_lines = TransactionLines.objects.filter(transaction_uuid__in = txns)

        # Filter 2
        if has_demographic == "1":
            txn_lines = txn_lines.filter(has_demographics = True)
        elif has_demographic == "0":
            txn_lines = txn_lines.filter(has_demographics = False)
        else:
            print("No has_demographic filter found.")


        # Filter 3
        if set(['from', 'to']).issubset(set(request.query_params.keys())):
            print("found from date & to date filters")
            fmt = "%d.%m.%Y %H:%M"
            t_zone = request.query_params.get('timezone')

            created_at_from = request.query_params.get('from')
            created_at_to = request.query_params.get('to')

            if t_zone:
                time_zone = pytz.timezone(request.query_params.get('timezone'))

                created_at_from = time_zone.localize(datetime.strptime(created_at_from, fmt))

                created_at_from_utc = created_at_from.astimezone(pytz.utc)

                created_at_to = time_zone.localize(datetime.strptime(created_at_to, fmt))

                created_at_to_utc = created_at_to.astimezone(pytz.utc)
            else:
                # Default taking UTC timezone
                created_at_from_utc = datetime.strptime(created_at_from, fmt).astimezone(pytz.utc)

                created_at_to_utc = datetime.strptime(created_at_to, fmt).astimezone(pytz.utc)

            txn_lines = txn_lines.filter(created_at__gte = created_at_from_utc, created_at__lte = created_at_to_utc)
        else:
            print("No from date & to date filters are found.")

        if extended == "1":
            serializer = ExtendedTransactionLinesSerializer(txn_lines, many = True)
        else:
            serializer = TransactionLinesSerializer(txn_lines, many = True)

        if meta_flat == '1':
            response_data = process_serializer_data(serializer.data)
        else:
            response_data = serializer.data

        return Response(response_data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

class ProductApiView(APIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)

    def post(self, request):
        """
            Description :
            ----------
                Create New Product.

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)


            Request Method :
            ----------
                POST

            Request URL :
            ----------
                Case-1 : /api/v1/product/?/api_key=<client_api_key>

                *** OR ***

                Case-2 : /api/v1/product/

            Request Parameters :
            ----------
                {
                    "name" : "coca cola",                               // optional
                    "client_product_sku" : "beverage_1",                // required & Uniq
                    "client_product_category_sku" : "soft_drinks",      // required & Uniq
                }


            Response :
            ----------
                {
                    "uuid": "c46d5259-c4b2-4e5f-8e9e-a67f92043d8f",
                    "name": "coca cola",
                    "client_product_sku": "beverage_1",
                    "client_product_category_sku": "soft_drinks",
                    "client_uuid": "786f9129-279d-4e50-a83d-2028d6ccd7da"
                }

            Success Response Code :
            ----------
                201

            Error Response Code :
            ----------
                400

            Note: API Key is must (Either in Query Params Or Body)
            ----------
        """
        try:
            api_key = fetch_api_key_with_body_param(request)
            client_uuid = Client.objects.get(client_api_key = api_key).uuid
            request.data['client_uuid'] = client_uuid

            serializer = self.serializer_class(data = request.data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status = status.HTTP_201_CREATED)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        """
            Description :
            ----------
                Get Details of Product

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)

            Request Method :
            ----------
                GET

            Request URL :
            ----------
                Case-1 : api/v1/product/?api_key=<client_api_key>&product_uuid=<product_uuid>

                *** OR ***

                Case-2 : api/v1/product/?product_uuid=<product_uuid>

            Request Parameters :
            ----------
                -

            Response :
            ----------
                {
                    "uuid": "e6d09d39-f267-4715-9693-ea8ce3e9106e",
                    "name": "p1",
                    "client_product_sku": "Client product sku:",
                    "client_product_category_sku": "Client product category sku:"
                }

            Success Response Code :
            ----------
                200

            Error Response Code :
            ----------
                400
        """

        try:
            product_uuid = request.query_params.get('product_uuid')
            client_uuid = find_client_uuid(request)
            product = Product.objects.get(uuid = product_uuid, client_uuid = client_uuid)
            serializer = self.serializer_class(product)

            return Response(serializer.data, status = status.HTTP_200_OK)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """
            Description :
            ----------
                Delete Product

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)

            Request Method :
            ----------
                DELETE

            Request URL :
            ----------
                Case-1 : api/v1/product/?api_key=<client_api_key>&product_uuid=<product_uuid>

                *** OR ***

                Case-2 : api/v1/product/?product_uuid=<product_uuid>

            Request Parameters :
            ----------
                -

            Response :
            ----------
                {
                    "success": "true",
                    "message": "Product deleted Successfully."
                }

            Success Response Code :
            ----------
                301

            Error Response Code :
            ----------
                400
        """

        try:
            product_uuid = request.query_params.get('product_uuid')
            client_uuid = find_client_uuid(request)
            product = Product.objects.get(uuid = product_uuid, client_uuid = client_uuid)
            product.delete()

            return Response({"success": 'true', 'message': 'Product deleted Successfully.'}, status = status.HTTP_301_MOVED_PERMANENTLY)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def fetch_products(request):
    """
        Description :
        ----------
            Get list of Products

        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : api/v1/products/?api_key=<client_api_key>

            *** OR ***

            Case-2 : api/v1/products/

        Request Parameters :
        ----------
            -

        Response :
        ----------
           [
                {
                    "uuid": "4b781dde-01df-4b0e-9d49-57296c172ddf",
                    "name": "product2",
                    "client_product_sku": "Client product sku1",
                    "client_product_category_sku": "Client product category sku1",
                    "client_uuid": "e53f7385-f660-49ad-9b48-b660af001e96"
                },
                {
                    "uuid": "f042b087-01a9-448a-a240-37eb1290777f",
                    "name": "product1",
                    "client_product_sku": "Client product sku",
                    "client_product_category_sku": "Client product category sku",
                    "client_uuid": "e53f7385-f660-49ad-9b48-b660af001e96"
                }
            ]

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400
    """
    try:
        client_uuid = find_client_uuid(request)

        products = Product.objects.filter(client_uuid = client_uuid)
        serializer = ProductSerializer(products, many = True)

        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

class ProductCategoryApiView(APIView):
    serializer_class = ProductCategorySerializer

    permission_classes = (AllowAny,)

    def post(self, request):
        """
            Description :
            ----------
                Create New ProductCategory.

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)

            Request Method :
            ----------
                POST

            Request URL :
            ----------
                Case-1 : /api/v1/product_category/?api_key=<client_api_key>

                *** OR ***

                Case-2 : /api/v1/product_category/

            Request Parameters :
            ----------
                {
                    "name":"Soft Drink",                                        // optional
                    "client_product_category_sku": "soft_drinks",               // required & Uniq
                }

            Response :
            ----------
                {
                    "uuid": "503335da-74e9-42ae-a1e9-c0b6de214116",
                    "name": "Soft Drink",
                    "client_product_category_sku": "soft_drinks",
                    "client_uuid": "786f9129-279d-4e50-a83d-2028d6ccd7da"
                }

            Success Response Code :
            ----------
                201

            Error Response Code :
            ----------
                400

            Note: API Key is must (Either in Query Params Or Body)
            ----------
        """
        try:
            api_key = fetch_api_key_with_body_param(request)
            client_uuid = Client.objects.get(client_api_key = api_key).uuid
            request.data['client_uuid'] = client_uuid

            serializer = self.serializer_class(data = request.data)
            serializer.is_valid(raise_exception = True)
            serializer.save()

            return Response(serializer.data, status = status.HTTP_201_CREATED)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        """
            Description :
            ----------
                Get Details of ProductCategory

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)

            Request Method :
            ----------
                GET

            Request URL :
            ----------
                Case-1 : api/v1/productCategory/?api_key=<client_api_key>&product_category_uuid=<product_category_uuid>

                *** OR ***

                Case-2 : api/v1/productCategory/?product_category_uuid=<product_category_uuid>

            Request Parameters :
            ----------
                -

            Response :
            ----------
                {
                    "uuid": "2523b11b-6036-458a-8e3c-1ed2f28b1d40",
                    "name": "pc1",
                    "client_product_category_sku": "Client product category sku:"
                }

            Success Response Code :
            ----------
                200

            Error Response Code :
            ----------
                400
        """

        try:
            product_category_uuid = request.query_params.get('product_category_uuid')
            client_uuid = find_client_uuid(request)
            product_category = ProductCategory.objects.get(uuid = product_category_uuid, client_uuid = client_uuid)
            serializer = self.serializer_class(product_category)

            return Response(serializer.data, status = status.HTTP_200_OK)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """
            Description :
            ----------
                Delete ProductCategory

            Header :
            ----------
                Content-Type    : application/json
                api-key         : client_api_key        (Must in Case-2 Request URL)

            Request Method :
            ----------
                DELETE

            Request URL :
            ----------
                Case-1 : api/v1/product_category/?api_key=<client_api_key>&product_category_uuid=<product_category_uuid>

                *** OR ***

                Case-2 : api/v1/product_category/?product_category_uuid=<product_category_uuid>

            Request Parameters :
            ----------
                -

            Response :
            ----------
                {
                    "success": "true",
                    "message": "Product Category deleted Successfully."
                }

            Success Response Code :
            ----------
                301

            Error Response Code :
            ----------
                400
        """

        try:
            product_category_uuid = request.query_params.get('product_category_uuid')
            client_uuid = find_client_uuid(request)
            product_category = ProductCategory.objects.get(uuid = product_category_uuid, client_uuid = client_uuid)
            product_category.delete()

            return Response({"success": 'true', 'message': 'Product Category deleted Successfully.'}, status = status.HTTP_301_MOVED_PERMANENTLY)
        except Exception as err:
            return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes((AllowAny,))
def fetch_product_categories(request):
    """
        Description :
        ----------
            Get Details of ProductCategories

        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : api/v1/product_categories/?api_key=<client_api_key>

            *** OR ***

            Case-2 : api/v1/product_categories/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            [
                {
                    "uuid": "7ceb0e8e-9ccb-4879-8e45-b1cf236f2498",
                    "name": "product category2",
                    "client_product_category_sku": "Client product category sku1",
                    "client_uuid": "e53f7385-f660-49ad-9b48-b660af001e96"
                },
                {
                    "uuid": "08048846-06d9-4eb7-8e1c-8b0172fbe0b6",
                    "name": "product category",
                    "client_product_category_sku": "Client product category sku",
                    "client_uuid": "e53f7385-f660-49ad-9b48-b660af001e96"
                }
            ]

        Success Response Code :
        ----------
            200

        Error Response Code :
        ----------
            400
    """

    try:
        client_uuid = find_client_uuid(request)
        product_categories = ProductCategory.objects.filter(client_uuid = client_uuid)
        serializer = ProductCategorySerializer(product_categories, many = True)

        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)

# TODO: Make a new py file for ClientUser as 'client_user_apis.py'
@api_view(['GET'])
# @authentication_classes((TokenAuthentication , SessionAuthentication))
@permission_classes((AllowAny,))
def bundle_dashboard_api(request):
    try:
        bundle_data = []
        # client_user = Client.objects.get(user = request.user)
        client_user = Client.objects.first()
        stores = Store.objects.filter(client_uuid = client_user).count()
        transactions = Transaction.objects.filter(client_uuid = client_user)

        current_week = datetime.today().isocalendar()[1]
        start_of_month = datetime.today().replace(day=1)
        today = datetime.now().date()
        tomorrow = today + timedelta(1)
        today_start = datetime.combine(today, time())
        today_end = datetime.combine(tomorrow, time())
        last_month = today.month - 1 if today.month>1 else 12
        last_month_year = today.year if today.month > last_month else today.year - 1

        current_week_count = transactions.filter(created_at__week=current_week).count()
        current_month_count = transactions.filter(created_at__gte=start_of_month).count()
        today_count = transactions.filter(created_at__lte=today_end, created_at__gte=today_start).count()
        last_month_count = transactions.filter(created_at__year=last_month_year, created_at__month=last_month).count()

        
        bundle_data.append({'stores': stores, 'current_week_count' : current_week_count, 'current_month_count' : current_month_count, 'today_count' : today_count, 'last_month_count' : last_month_count })

        return Response(bundle_data, status = status.HTTP_200_OK)
    except Exception as e:
        raise


@api_view(['GET'])
@permission_classes((AllowAny,))
def stores(request):
    """
        Description :
        ----------
            Return all stores of the client
        Header :
        ----------
            Content-Type    : application/json
            api-key         : client_api_key        (Must in Case-2 Request URL)

        Request Method :
        ----------
            GET

        Request URL :
        ----------
            Case-1 : /api/v1/stores/?api_key=<client_api_key>

            *** OR ***

            Case-2 : /api/v1/stores/

        Request Parameters :
        ----------
            -

        Response :
        ----------
            List of stores in JSON format

        Success Response Code :
        ----------
            201

        Error Response Code :
        ----------
            400

        Note: API Key is must (Either in Query Params OR Header)
        ----------
    """
    try:
        client_uuid = find_client_uuid(request)
        stores = Store.objects.filter(client_uuid = client_uuid)
        serializer = StoreSerializer(stores, many = True)

        return Response(serializer.data, status = status.HTTP_200_OK)
    except Exception as err:
        return Response(err.args, status = status.HTTP_400_BAD_REQUEST)


# ***** Start Re-usable methods *****

def find_client_uuid(request):
    api_key = fetch_api_key_for_get_request(request)

    # Find Client using API Key & return UUID of Client
    return find_client(api_key).uuid

def find_client(api_key):
    return Client.objects.get(client_api_key = api_key)

def fetch_api_key_for_get_request(request):
    http_api_key = request.META.get("HTTP_API_KEY")
    query_api_key = request.query_params.get('api_key')
    # Check api_key either into Headers OR Query Parameters, if not found then return
    if http_api_key != None:
        return http_api_key
    elif query_api_key != None:
        return query_api_key
    else:
        raise Exception({"Message": "Please provide API Key (either Header with 'api-key' OR Query Params with 'api_key')"}, status.HTTP_400_BAD_REQUEST)

# Fetches API key which can be into http_header, query_params or body_params
def fetch_api_key_with_body_param(request):
    http_api_key = request.META.get("HTTP_API_KEY")
    query_api_key = request.query_params.get('api_key')
    try:
        body_api_key = request.data['api_key']
    except Exception as err:
        body_api_key = None

    # Check api_key which can be into Headers OR Query Parameters OR Body Parameters, if not found then Raise Exception
    if http_api_key != None:
        return http_api_key
    elif query_api_key != None:
        return query_api_key
    elif body_api_key != None:
        return body_api_key
    else:
        raise Exception({"Message": "Please provide API Key (Header with 'api-key' OR Query Params with 'api_key' OR Body with 'api_key')"}, status.HTTP_400_BAD_REQUEST)

# Example :
# Original => {"meta": [{"color": "red", "color3": "red" }]}
# Converted => {"meta_color": "red", "meta_color3": "red"}
def process_serializer_data(serializer_data):
    for obj in serializer_data:
        if obj["meta"]:
            for pair in obj["meta"]:
                new_meta = { k.replace(k, ('meta_'+k)): v for k, v in pair.items() }
            # Add new pairs of meta into obj.
            obj.update(new_meta)
            # Remove meta key from dict
            obj.pop('meta', None)
    return serializer_data

# ***** End Re-usable methods *****
