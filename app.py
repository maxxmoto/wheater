import os
import json
import requests
from flask import Flask, render_template, request, jsonify
from yandex_weather import parse_yandex

app = Flask(__name__)

WEATHERAPI_KEY = '0426384116734bb4a94183926263007'
GEOAPIFY_KEY = 'acd79c1eab9249aebd6287e34e67f703'

WEATHERAPI_BASE = 'http://api.weatherapi.com/v1'
GEOAPIFY_BASE = 'https://api.geoapify.com/v1/geocode/search'

CONDITION_TO_ICON = {
    1000: 'sun', 1003: 'cloud-sun', 1006: 'cloud', 1009: 'cloud',
    1030: 'cloud', 1063: 'cloud-rain', 1066: 'snowflake',
    1069: 'cloud-rain', 1072: 'cloud-rain', 1087: 'cloud-lightning',
    1114: 'snowflake', 1117: 'snowflake', 1135: 'cloud', 1147: 'cloud',
    1150: 'cloud-rain', 1153: 'cloud-rain', 1168: 'cloud-rain',
    1171: 'cloud-rain', 1180: 'cloud-rain', 1183: 'cloud-rain',
    1186: 'cloud-rain', 1189: 'cloud-rain', 1192: 'cloud-rain',
    1195: 'cloud-rain', 1198: 'cloud-rain', 1201: 'cloud-rain',
    1204: 'cloud-rain', 1207: 'cloud-rain', 1210: 'snowflake',
    1213: 'snowflake', 1216: 'snowflake', 1219: 'snowflake',
    1222: 'snowflake', 1225: 'snowflake', 1237: 'cloud-rain',
    1240: 'cloud-rain', 1243: 'cloud-rain', 1246: 'cloud-rain',
    1249: 'cloud-rain', 1252: 'cloud-rain', 1255: 'snowflake',
    1258: 'snowflake', 1261: 'cloud-rain', 1264: 'cloud-rain',
    1273: 'cloud-lightning', 1276: 'cloud-lightning',
    1279: 'cloud-lightning', 1282: 'cloud-lightning',
}

WIND_DIRECTIONS = [
    'С', 'ССВ', 'СВ', 'ВСВ', 'В', 'ВЮВ', 'ЮВ', 'ЮЮВ',
    'Ю', 'ЮЮЗ', 'ЮЗ', 'ЗЮЗ', 'З', 'ЗСЗ', 'СЗ', 'ССЗ',
]


def geocode(city):
    resp = requests.get(GEOAPIFY_BASE, params={
        'text': city, 'apiKey': GEOAPIFY_KEY, 'lang': 'ru', 'limit': 1
    }, timeout=5)
    if resp.status_code != 200:
        return None, None, None, None, 'Ошибка сервиса геокодирования'

    data = resp.json()
    features = data.get('features', [])
    if not features:
        return None, None, None, None, f'Город "{city}" не найден'

    props = features[0]['properties']
    lat = props['lat']
    lon = props['lon']
    city_name = props.get('city') or props.get('name', city)
    city_name = city_name.replace('Городской округ ','').strip()
    country = props.get('country', '')
    elevation = 0
    try:
        elev_resp = requests.get(
            'https://api.open-elevation.com/api/v1/lookup',
            params={'locations': f'{lat},{lon}'}, timeout=3
        )
        if elev_resp.status_code == 200:
            elevation = elev_resp.json()['results'][0]['elevation']
    except Exception:
        pass
    label = f'{city_name}, {country}' if country else city_name
    label = label.replace(', Россия','').replace(', Russia','').strip()
    return lat, lon, elevation, label, None


def get_icon(code, is_day):
    icon = CONDITION_TO_ICON.get(code, 'cloud')
    if icon == 'sun' and not is_day:
        return 'moon'
    if icon == 'cloud-sun' and not is_day:
        return 'cloud-moon'
    return icon


def get_weather(lat, lon, city_label):
    resp = requests.get(f'{WEATHERAPI_BASE}/forecast.json', params={
        'key': WEATHERAPI_KEY, 'q': f'{lat},{lon}',
        'days': 8, 'lang': 'ru', 'aqi': 'no', 'alerts': 'no',
    }, timeout=10)

    if resp.status_code != 200:
        return None

    d = resp.json()
    current = d['current']
    forecast = d['forecast']['forecastday']
    is_day = current.get('is_day', 1)

    uv_val = current.get('uv', 0)
    if uv_val <= 2:
        uv_level, uv_desc = 'Низкий', 'Безопасно для большинства.'
    elif uv_val <= 5:
        uv_level, uv_desc = 'Умеренный', 'Оставайтесь в тени в полуденное время.'
    elif uv_val <= 7:
        uv_level, uv_desc = 'Высокий', 'Защита обязательна.'
    elif uv_val <= 10:
        uv_level, uv_desc = 'Очень высокий', 'Примите дополнительные меры защиты.'
    else:
        uv_level, uv_desc = 'Экстремальный', 'Избегайте пребывания на солнце.'

    sunrise = forecast[0]['astro']['sunrise'].replace(' AM', '').replace(' PM', '')
    sunset = forecast[0]['astro']['sunset'].replace(' AM', '').replace(' PM', '')

    hourly = []
    if forecast:
        hours = forecast[0].get('hour', [])
        for i, h in enumerate(hours):
            time_parts = h['time'].split()
            time_label = time_parts[1] if len(time_parts) > 1 else h['time']
            hourly.append({
                'time': 'Сейчас' if i == 0 else time_label,
                'temp': round(h['temp_c']),
                'icon': get_icon(h['condition']['code'], h.get('is_day', 1)),
            })
        hourly = hourly[::3][:8]
        if hourly and hourly[0]['time'] != 'Сейчас':
            hourly.insert(0, {
                'time': 'Сейчас',
                'temp': round(current['temp_c']),
                'icon': get_icon(current['condition']['code'], is_day),
            })
            hourly = hourly[:8]

    day_names = ['Сегодня', 'Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб']
    daily = []
    for i, day in enumerate(forecast[:8]):
        label = day_names[i] if i < len(day_names) else day['date']
        item = {
            'day': label,
            'low': round(day['day']['mintemp_c']),
            'high': round(day['day']['maxtemp_c']),
            'icon': get_icon(day['day']['condition']['code'], 1),
            'precip': day['day']['daily_chance_of_rain'],
        }
        if i == 0:
            item['currentTemp'] = round(current['temp_c'])
        daily.append(item)

    week_low = min(d['low'] for d in daily)
    week_high = max(d['high'] for d in daily)

    return {
        'current': {
            'city': city_label,
            'temp': round(current['temp_c']),
            'condition': current['condition']['text'].capitalize(),
            'high': round(forecast[0]['day']['maxtemp_c']),
            'low': round(forecast[0]['day']['mintemp_c']),
        },
        'hourly': hourly,
        'daily': daily,
        'details': {
            'uvIndex': {
                'value': round(uv_val),
                'level': uv_level,
                'description': uv_desc,
            },
            'wind': {
                'speed': round(current['wind_kph'] / 3.6, 1),
                'direction': current['wind_dir'],
                'degree': current.get('wind_degree', 0),
                'gust': round(current.get('gust_kph', 0) / 3.6, 1),
            },
            'sunrise': sunrise.strip(),
            'sunset': sunset.strip(),
            'humidity': current['humidity'],
            'visibility': current['vis_km'],
            'pressure': round(current['pressure_mb']),  # in mb, converted to mmHg in index()
            'feelsLike': round(current['feelslike_c']),
        },
        'weekMin': week_low,
        'weekMax': week_high,
    }


def create_mock_data():
    return {
        'current': {
            'city': 'Москва', 'temp': 24, 'condition': 'Преимущественно солнечно',
            'high': 26, 'low': 14,
        },
        'hourly': [
            {'time': 'Сейчас', 'temp': 24, 'icon': 'sun'},
            {'time': '13:00', 'temp': 25, 'icon': 'sun'},
            {'time': '14:00', 'temp': 26, 'icon': 'cloud'},
            {'time': '15:00', 'temp': 26, 'icon': 'cloud'},
            {'time': '16:00', 'temp': 25, 'icon': 'cloud-rain'},
            {'time': '17:00', 'temp': 23, 'icon': 'cloud-rain'},
            {'time': '18:00', 'temp': 21, 'icon': 'cloud'},
            {'time': '19:00', 'temp': 19, 'icon': 'sun'},
        ],
        'daily': [
            {'day': 'Сегодня', 'low': 14, 'high': 26, 'icon': 'sun', 'currentTemp': 24, 'precip': 0},
            {'day': 'Вс', 'low': 16, 'high': 28, 'icon': 'sun', 'precip': 0},
            {'day': 'Пн', 'low': 15, 'high': 22, 'icon': 'cloud-rain', 'precip': 60},
            {'day': 'Вт', 'low': 12, 'high': 19, 'icon': 'cloud', 'precip': 20},
            {'day': 'Ср', 'low': 13, 'high': 21, 'icon': 'sun', 'precip': 0},
            {'day': 'Чт', 'low': 15, 'high': 24, 'icon': 'cloud', 'precip': 10},
            {'day': 'Пт', 'low': 17, 'high': 25, 'icon': 'cloud-lightning', 'precip': 80},
            {'day': 'Сб', 'low': 16, 'high': 27, 'icon': 'sun', 'precip': 0},
        ],
        'details': {
            'uvIndex': {'value': 5, 'level': 'Умеренный', 'description': 'Оставайтесь в тени в полуденное время.'},
            'wind': {'speed': 4.2, 'direction': 'СЗ', 'degree': 315, 'gust': 7.2},
            'sunrise': '05:20', 'sunset': '21:14',
            'humidity': 45, 'visibility': 10, 'pressure': {'value': 755, 'norm': 758, 'diff': -3}, 'feelsLike': 23,
        },
        'weekMin': 12, 'weekMax': 28,
    }


@app.route('/api/cities')
def api_cities():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'cities': []})

    try:
        resp = requests.get('https://api.geoapify.com/v1/geocode/autocomplete', params={
            'text': q, 'apiKey': GEOAPIFY_KEY,
            'lang': 'ru', 'limit': 10, 'type': 'city',
            'filter': 'countrycode:ru',
        }, timeout=3)

        if resp.status_code != 200:
            return jsonify({'cities': []})

        data = resp.json()
        results = []
        seen = set()
        for feat in data.get('features', []):
            p = feat['properties']
            name = p.get('city') or p.get('name', '')
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            region = p.get('state', '') or p.get('county', '') or ''
            lat = p.get('lat')
            lon = p.get('lon')
            results.append({
                'name': name,
                'region': region,
                'lat': lat,
                'lon': lon,
            })

        return jsonify({'cities': results[:10]})
    except Exception:
        return jsonify({'cities': []})


@app.route('/')
def index():
    city = request.args.get('city', 'Москва')
    error = None
    data = None

    try:
        lat, lon, elevation, city_label, geo_error = geocode(city)
        if geo_error:
            error = geo_error
        else:
            data = get_weather(lat, lon, city_label)
            if data is None:
                error = 'Ошибка получения данных о погоде. Попробуйте позже.'
            else:
                def mb_to_mmhg(mb_val):
                    return round(mb_val / 1.33322, 1)

                norm_mb = 1013.25 - (elevation / 100) * 11.3
                current_mb = data['details']['pressure']
                current_mmhg = mb_to_mmhg(current_mb)
                norm_mmhg = mb_to_mmhg(norm_mb)
                diff = round(current_mmhg - norm_mmhg, 1)
                data['details']['pressure'] = {
                    'value': current_mmhg,
                    'norm': norm_mmhg,
                    'diff': diff,
                }
                if abs(diff) >= 10:
                    if diff > 0:
                        data['details']['pressure']['warning'] = 'Давление выше нормы на ' + str(abs(diff)) + ' мм. Людям с сердечно-сосудистыми заболеваниями стоит быть внимательнее.'
                    else:
                        data['details']['pressure']['warning'] = 'Давление ниже нормы на ' + str(abs(diff)) + ' мм. Возможны головные боли и ухудшение самочувствия у метеозависимых.'
                try:
                    city_ru = city_label.split(',')[0].strip()
                    try:
                        with open('russian_cities.json', 'r', encoding='utf-8') as _f:
                            _cities = json.load(_f)
                        _match = next((c for c in _cities if c.get('city_ru', '').lower() == city_ru.lower()), None)
                        _city_for_yandex = _match.get('city', city_ru) if _match else city_ru
                    except Exception:
                        _city_for_yandex = city_ru
                    yandex_data = parse_yandex(_city_for_yandex)
                    if yandex_data:
                        if yandex_data.get('magnetic') and yandex_data['magnetic'][0] is not None:
                            data['details']['magnetic'] = {
                                'value': yandex_data['magnetic'][0],
                                'status': yandex_data['magnetic'][1],
                            }
                        if yandex_data.get('days') and len(yandex_data['days']) > 0:
                            data['yandexDays'] = yandex_data['days']
                except Exception:
                    pass
    except requests.exceptions.RequestException:
        error = 'Ошибка соединения. Проверьте подключение к интернету.'

    if data is None:
        data = create_mock_data()

    return render_template('index.html', data=data, error=error, search_city=city)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
