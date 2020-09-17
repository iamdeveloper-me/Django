import os, sys, requests

# Should work only for staging environment
if (os.environ.get('DJANGO_SETTINGS_MODULE') == 'retailquant.settings.staging'):
    sys.path.append('/home/ubuntu/Projects/customer_matcher_engine/luna-3.6.4/')
    import match

# Should work only for production environment
if (os.environ.get('DJANGO_SETTINGS_MODULE') == 'retailquant.settings.production'):
    sys.path.append('/home/ubuntu/Projects/luna-sdk_ub1404_rel_v.3.6.7/')
    import match

from userprofile.rest_framework_import import *
from organizations.models import Sensor, DemographicData, Firmware, Store, Weather
from organizations.serializers import *
from datetime import datetime, time, timedelta
# from celery.contrib import rdb

# ***** Start Celery Job Methods *****

def demographic_data_matching():
    try:
        txns = Transaction.objects.filter(matcher_has_run = False)

        for txn in txns:
            # Find POS using Transaction's client_pos_uuid
            pos = PointOfSale.objects.get(client_pos_uuid = txn.client_pos_uuid)
            if pos.sensor_uuid is None:
                print("Updating 'matcher_has_run' to True")
                txn.matcher_has_run = True
                txn.save()
                # Find TransactionLines to update same above attributes
                transaction_lines = TransactionLines.objects.filter(transaction_uuid = txn.uuid)
                transaction_lines.update(matcher_has_run = True)
            else:
                # Find offset time from POS
                seconds_offset = pos.seconds_offset
                # Calculating offset time
                txn_purchased_at = txn.purchased_at - timedelta(seconds = seconds_offset)

                # Find DemographicData
                demographic_objects = DemographicData.objects.filter(start_rec_at__lt = txn_purchased_at, stop_rec_at__gt = txn_purchased_at, sensor_uuid=pos.sensor_uuid).order_by('created_at')
                if demographic_objects:
                    print("Updating 'matcher_has_run' & 'demographic_data' to True and age, gender etc from Mached Demographic data to Transaction.")
                    # Picking first DemographicData
                    demographic_object = demographic_objects[0]

                    # Set fields from mached DemographicData into Transaction and update 'matcher_has_run' & 'demographic_data' to True
                    txn.matcher_has_run  = True
                    txn.has_demographics = True
                    txn.age              = demographic_object.age
                    txn.gender           = demographic_object.gender
                    txn.start_rec_at     = demographic_object.start_rec_at
                    txn.stop_rec_at      = demographic_object.stop_rec_at
                    txn.duration         = demographic_object.duration
                    txn.glasses          = demographic_object.glasses
                    txn.ethnicity        = demographic_object.ethnicity
                    txn.times_resumed    = demographic_object.times_resumed
                    txn.min_smile        = demographic_object.min_smile
                    txn.avg_smile        = demographic_object.avg_smile
                    txn.max_smile        = demographic_object.max_smile
                    txn.min_happiness    = demographic_object.min_happiness
                    txn.avg_happiness    = demographic_object.avg_happiness
                    txn.max_happiness    = demographic_object.max_happiness
                    txn.min_surprise     = demographic_object.min_surprise
                    txn.avg_surprise     = demographic_object.avg_surprise
                    txn.max_surprise     = demographic_object.max_surprise
                    txn.min_fear         = demographic_object.min_fear
                    txn.avg_fear         = demographic_object.avg_fear
                    txn.max_fear         = demographic_object.max_fear
                    txn.min_anger        = demographic_object.min_anger
                    txn.avg_anger        = demographic_object.avg_anger
                    txn.max_anger        = demographic_object.max_anger
                    txn.min_neutral      = demographic_object.min_neutral
                    txn.avg_neutral      = demographic_object.avg_neutral
                    txn.max_neutral      = demographic_object.max_neutral
                    txn.avg_disgust      = demographic_object.avg_disgust
                    txn.max_disgust      = demographic_object.max_disgust
                    txn.min_disgust      = demographic_object.min_disgust
                    txn.face_descriptor  = demographic_object.face_descriptor

                    txn.save()

                    # Find TransactionLines to update same above attributes
                    transaction_lines = TransactionLines.objects.filter(transaction_uuid = txn.uuid)
                    transaction_lines.update(
                        matcher_has_run     = True,
                        has_demographics    = True,
                        age                 = demographic_object.age,
                        gender              = demographic_object.gender,
                        start_rec_at        = demographic_object.start_rec_at,
                        stop_rec_at         = demographic_object.stop_rec_at,
                        duration            = demographic_object.duration,
                        glasses             = demographic_object.glasses,
                        ethnicity           = demographic_object.ethnicity,
                        times_resumed       = demographic_object.times_resumed,
                        min_smile           = demographic_object.min_smile,
                        avg_smile           = demographic_object.avg_smile,
                        max_smile           = demographic_object.max_smile,
                        min_happiness       = demographic_object.min_happiness,
                        avg_happiness       = demographic_object.avg_happiness,
                        max_happiness       = demographic_object.max_happiness,
                        min_surprise        = demographic_object.min_surprise,
                        avg_surprise        = demographic_object.avg_surprise,
                        max_surprise        = demographic_object.max_surprise,
                        min_fear            = demographic_object.min_fear,
                        avg_fear            = demographic_object.avg_fear,
                        max_fear            = demographic_object.max_fear,
                        min_anger           = demographic_object.min_anger,
                        avg_anger           = demographic_object.avg_anger,
                        max_anger           = demographic_object.max_anger,
                        min_neutral         = demographic_object.min_neutral,
                        avg_neutral         = demographic_object.avg_neutral,
                        avg_disgust         = demographic_object.avg_disgust,
                        max_neutral         = demographic_object.max_neutral,
                        max_disgust         = demographic_object.max_disgust,
                        min_disgust         = demographic_object.min_disgust
                    )
                else:
                    print("Updating 'matcher_has_run' to True")
                    txn.matcher_has_run = True
                    txn.save()

                    # Find TransactionLines to update same above attributes
                    transaction_lines = TransactionLines.objects.filter(transaction_uuid = txn.uuid)
                    transaction_lines.update(matcher_has_run = True)

    except Exception as err:
        print("Incounted error: ", err.args)

def customer_matching():
    # Should work only for production environment
    if (os.environ.get('DJANGO_SETTINGS_MODULE') != 'retailquant.settings.development'):
        print("***** Start 'customer_matching' *****")
        try:
            txns = Transaction.objects.filter(has_demographics = True, customer_matched = False)

            customer_uuid_with_face = { str(cust.pk):cust.face_descriptor for cust in Customer.objects.all() }

            for txn in txns:
                # Face Decriptor of Transaction
                txn_face_decr = txn.face_descriptor

                # Check if txn_face_decr is present
                if txn_face_decr != None and txn_face_decr != '':
                    print("Transaction's face_descriptor: ", txn_face_decr)

                    # Match customer using c++ function
                    best_match_customer_uuid = match.findMatch( txn_face_decr, match.map_string_string( customer_uuid_with_face ), 0.96 )
                    print("Best Matched Customer's UUID: ", best_match_customer_uuid)

                    if best_match_customer_uuid in [None, '']:
                        print("Creating new Customer.")

                        matched_customer = Customer.objects.create(face_descriptor = txn_face_decr, client_uuid = txn.client_uuid, registered_at = txn.purchased_at)
                    else:
                        print( "Best match for Customers Dict: ".format( txn_face_decr, best_match_customer_uuid, customer_uuid_with_face[best_match_customer_uuid] ) )

                        matched_customer = Customer.objects.get(uuid = best_match_customer_uuid)

                    print("Updating Transaction's customer_uuid")
                    # Set customer_matched to be True (don't care it is new created customer or existing customer)
                    txn.customer_matched = True

                    # Update Transaction customer_uuid
                    txn.customer_uuid    = matched_customer
                    txn.save()

                    print("Updating TransactionLines's customer_uuid")
                    # Find TransactionLines for iterated Transaction object.
                    transaction_lines = TransactionLines.objects.filter(transaction_uuid = txn.uuid, has_demographics = True, customer_matched = False)

                    # Update TransactionLines customer_matched & customer_uuid
                    transaction_lines.update(customer_matched = True, customer_uuid = matched_customer)

                    # Instert entries into CustomerVisit
                    create_customer_visit(matched_customer, txn)
                else:
                    print("Matched Cusotmer not found due to 'face_descriptor' is blank for Transaction UUID: ", txn.uuid)
            print("***** Finish 'customer_matching' *****")
        except Exception as err:
            print("Incounted error: ", err.args)
    else:
        print("customer_matching() could not be run due to current Environment is not Production.")

# TODO: Check last date weather fetching 
def fetches_weather_data():
    try:
        stores = Store.objects.all()
        yesterday_timstamp = str(int((datetime.combine(datetime.today(), time.min) - timedelta(days=1)).timestamp()))

        print(yesterday_timstamp, datetime.utcfromtimestamp(int((datetime.combine(datetime.today(), time.min) - timedelta(days=1)).timestamp())))

        for store in stores:
            latitude, longitude = str(store.location.y), str(store.location.x)
            res = requests.get('https://api.darksky.net/forecast/0ab36df4c3f160ff5630ad3d3fb8687c/'+ latitude + ',' + longitude + ',' + yesterday_timstamp + '?exclude=currently,flags')
            if res.status_code == 200 and 'hourly' in res.json():
                try:
                    for data in res.json()['hourly']['data']:
                        data['store_uuid'] = store.uuid
                        data['time'] = datetime.fromtimestamp(data['time'])
                        serializer = WeatherSerializer(data=data)
                        serializer.is_valid(raise_exception = True)
                        serializer.save()
                except Exception as e:
                    print("This store is " + str(store.pk) + " and time is " + str(data['time']) + " allready exists ! \n", e)
                    pass

            else:
                print("Hourly data is not available in weather data !")

    except Exception as e:
        raise

# transaction's purchased_at    /   weather's time
# 5:00 - 5:59                   /   5:30
# 6:00 - 6:59                   /   6:30
# 7:00 - 7:59                   /   7:30  
def weather_matching():
    print("***** start 'weather_matching' *****")
    try:
        txns = Transaction.objects.filter(weather_matcher_has_run = False, client_pos_uuid__isnull = False)
        # Get minutes from weather (because it may be 0 OR 30, so to make logic for Transaction & Weather matching.)
        base_weather_minutes = Weather.objects.last().time.minute

        for txn in txns:
            pos = PointOfSale.objects.filter(client_pos_uuid = txn.client_pos_uuid).first()

            if pos:
                store = pos.store_uuid
                txn_purchased_at = txn.purchased_at
                print("Transaction purchased_at: ", txn_purchased_at)
                txn_purchased_minute = txn_purchased_at.minute
                # Removes minute, second & microsecond from Transaction's purchase_at
                time_without_min = txn_purchased_at.replace(minute = 0, second = 0, microsecond = 0)

                # Condition for first half (0 min to 29 min) of an hour
                if (txn_purchased_minute >= (0 + base_weather_minutes) and txn_purchased_minute < (30 + base_weather_minutes)):
                    # Transaction's purchase_at without minute, second & microsecond (i.e. 2:00:00, 11:00:00 etc)
                    start_time = time_without_min
                    # Adding 29 minutes to Transaction's purchase_at (i.e. 2:29:00, 11:29:00 etc)
                    end_time = start_time + timedelta(minutes = 30)
                    print("Fetching first HALF of an Hour for Weather (start_time & end_time) :", start_time, end_time)
                # Condition for second half (30 min to 59 min) of an hour
                else:
                    # Adding 30 minutes to Transaction's purchase_at (i.e. 2:30:00, 11:30:00 etc)
                    start_time = time_without_min + timedelta(minutes = 30)
                    # Adding 59 minutes to Transaction's purchase_at (i.e. 2:59:00, 11:59:00 etc)
                    end_time = time_without_min + timedelta(hours = 1)
                    print("Fetching second HALF of an Hour for Weather (start_time & end_time) :", start_time, end_time)

                # Find weather (either in first half OR second half for an hour)
                weather = Weather.objects.filter(store_uuid = store, time__range = (start_time, end_time)).first()

                if weather:
                    print("Weather uuid: ", weather.uuid)
                    print("Weather time: ", weather.time)

                    txn.weather_matcher_has_run     = True
                    txn.weather_time                = weather.time
                    txn.weather_summary             = weather.summary
                    txn.weather_icon                = weather.icon
                    txn.weather_precipIntensity     = weather.precipIntensity
                    txn.weather_precipProbability   = weather.precipProbability
                    txn.precipAccumulation          = weather.precipAccumulation
                    txn.precipType                  = weather.precipType
                    txn.weather_temperature         = weather.temperature
                    txn.weather_apparentTemperature = weather.apparentTemperature
                    txn.weather_dewPoint            = weather.dewPoint
                    txn.weather_humidity            = weather.humidity
                    txn.weather_pressure            = weather.pressure
                    txn.weather_windSpeed           = weather.windSpeed
                    txn.windGust                    = weather.windGust
                    txn.weather_windBearing         = weather.windBearing
                    txn.weather_cloudCover          = weather.cloudCover
                    txn.weather_uvIndex             = weather.uvIndex
                    txn.weather_visibility          = weather.visibility
                    txn.ozone                       = weather.ozone

                    print("***** Updating Weather data for Transaction: *****", txn.uuid)
                    txn.save()

                    txn_lines = TransactionLines.objects.filter(transaction_uuid = txn.uuid)

                    txn_lines.update(
                            weather_matcher_has_run     = True,
                            weather_time                = weather.time,
                            weather_summary             = weather.summary,
                            weather_icon                = weather.icon,
                            weather_precipIntensity     = weather.precipIntensity,
                            weather_precipProbability   = weather.precipProbability,
                            precipAccumulation          = weather.precipAccumulation,
                            precipType                  = weather.precipType,
                            weather_temperature         = weather.temperature,
                            weather_apparentTemperature = weather.apparentTemperature,
                            weather_dewPoint            = weather.dewPoint,
                            weather_humidity            = weather.humidity,
                            weather_pressure            = weather.pressure,
                            weather_windSpeed           = weather.windSpeed,
                            windGust                    = weather.windGust,
                            weather_windBearing         = weather.windBearing,
                            weather_cloudCover          = weather.cloudCover,
                            weather_uvIndex             = weather.uvIndex,
                            weather_visibility          = weather.visibility,
                            ozone                       = weather.ozone
                        )
                else:
                    print("***** Weather Data not found for Transaction: *****", txn.uuid)
            else:
                print("***** POS not found for Transaction: *****", txn.uuid)

    except Exception as e:
        print("***** Got Exception *****")
        raise
    else:
        print("***** 'try' block passed successfully *****")
    finally:
        print("***** Finish 'weather_matching' *****")

# ***** End Celery Job Methods *****


# ***** Start Re-usable Methods *****

def create_customer_visit(customer, transaction):
    try:
        pos = PointOfSale.objects.get(client_pos_uuid = transaction.client_pos_uuid)
        store = pos.store_uuid
        cus_visit = CustomerVisit.objects.create(customer_uuid = customer, store_uuid = store, transaction_uuid = transaction, purchased_at = transaction.purchased_at)
        print("Creted CustomerVisit uuid: ", cus_visit.uuid)
    except Exception as e:
        print("Got Exception while Creating new CustomerVisit for Transaction's UUID & Erros: ", transaction.uuid, e)
        pass

# ***** End Re-usable Methods *****
