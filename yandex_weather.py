import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

YANDEX_BASE = 'https://yandex.ru/pogoda'
TIMEOUT = 5
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}


def _extract_magnetic(text):
    patterns = [
        r'магнитн[а-я]*\s*поле[^<]*?(\d+)',
        r'(\d+)\s*[–-]\s*(?:спокойн|неспокойн|буря)',
        r'Kp\s*[=:]\s*(\d+)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.DOTALL)
        if m:
            return int(m.group(1))

    for item in re.finditer(r'(\d+)', text):
        v = int(item.group(1))
        if 1 <= v <= 9:
            return v
    return None


def _magnetic_status(val):
    if val is None:
        return None, None
    if val <= 2:
        return val, 'Спокойное'
    elif val <= 4:
        return val, 'Неспокойное'
    elif val <= 6:
        return val, 'Слабая магнитная буря'
    elif val <= 8:
        return val, 'Магнитная буря'
    else:
        return val, 'Сильная магнитная буря'


def _extract_temp(text):
    m = re.search(r'([+\-−]?\d+)\s*°', text)
    if m:
        return int(m.group(1).replace('−', '-'))
    return None


TRANSLIT = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z',
    'и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts','ч':'ch','ш':'sh',
    'щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}


def _to_latin(text):
    text = text.lower().strip()
    result = []
    for ch in text:
        if ch in TRANSLIT:
            result.append(TRANSLIT[ch])
        elif ch.isalpha() or ch == '-':
            result.append(ch)
    return ''.join(result).replace('--', '-').strip('-')


def parse_yandex(city):
    slug = _to_latin(city)
    if not slug:
        return {'magnetic': (None, None), 'days': []}
    url = f'{YANDEX_BASE}/{slug}'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, 'lxml')
    page_text = soup.get_text()

    magnetic = _extract_magnetic(page_text)
    result = {'magnetic': _magnetic_status(magnetic), 'days': []}

    prefixes = ['m-', 'd-', 'e-', 'n-']
    slot_names = {'m-': 'утром', 'd-': 'днем', 'e-': 'вечером', 'n-': 'ночью'}

    temp_cells = soup.find_all('div', style=lambda s: s and any(p in s for p in [f'grid-area:{p}temp' for p in prefixes]))
    if not temp_cells:
        return result

    day_containers = {}
    for cell in temp_cells:
        parent = cell.find_parent(['div', 'li', 'article'], recursive=False)
        if not parent:
            parent = cell.parent
        while parent and parent.name != 'body':
            grand = parent.find_parent(['div', 'li', 'article'])
            if grand and grand.name == parent.name:
                parent = grand
            else:
                break
        pid = id(parent)
        if pid not in day_containers:
            day_containers[pid] = parent

    day_names = ['Сегодня', 'Завтра', 'Послезавтра']
    containers = list(day_containers.values())[:8]

    for day_idx, card in enumerate(containers):
        day_label = day_names[day_idx] if day_idx < 3 else None
        slots = []

        for prefix, time_name in slot_names.items():
            temp_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}temp' in s)
            if not temp_cell:
                continue
            temp = _extract_temp(temp_cell.get_text(' ', strip=True))
            if temp is None:
                continue

            feels = None
            feels_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}feels' in s)
            if feels_cell:
                ft = _extract_temp(feels_cell.get_text(' ', strip=True))
                if ft is not None:
                    feels = ft

            phenomenon = None
            text_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}text' in s)
            if text_cell:
                phenomenon = text_cell.get_text(' ', strip=True)[:60] or None

            wind = None
            wind_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}wind' in s)
            if wind_cell:
                wt = wind_cell.get_text(' ', strip=True)
                wm = re.search(r'(\d+[–-]\d+|\d+)', wt)
                if wm:
                    wind = wm.group(1) + ' м/с'
            dir_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}dir' in s)
            if dir_cell and wind:
                dt = dir_cell.get_text(' ', strip=True)
                wind += ' ' + dt

            pressure = None
            press_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}press' in s)
            if press_cell:
                pm = re.search(r'(\d{3,4})', press_cell.get_text(' ', strip=True))
                if pm:
                    pressure = int(pm.group(1))

            humidity = None
            hum_cell = card.find('div', style=lambda s: s and f'grid-area:{prefix}hum' in s)
            if hum_cell:
                hm = re.search(r'(\d+)', hum_cell.get_text(' ', strip=True))
                if hm:
                    humidity = int(hm.group(1))

            slots.append({
                'time': time_name,
                'temp': temp,
                'feels': feels,
                'phenomenon': phenomenon,
                'wind': wind,
                'pressure': pressure,
                'humidity': humidity,
            })

        if slots:
            day_info = {'slots': slots}
            if day_label:
                day_info['label'] = day_label
            result['days'].append(day_info)

    return result
