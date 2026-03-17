import requests
import json

LOCATION = "Egly,France"

WEATHER_CODES = {
    113: ("☀️", "Ensoleillé"),
    116: ("⛅", "Partiellement nuageux"),
    119: ("☁️", "Nuageux"),
    122: ("☁️", "Couvert"),
    143: ("🌫️", "Brouillard"),
    176: ("🌦️", "Averses légères"),
    179: ("🌨️", "Averses de neige"),
    182: ("🌧️", "Bruine verglaçante"),
    185: ("🌧️", "Bruine verglaçante"),
    200: ("⛈️", "Orages"),
    227: ("🌨️", "Chasse-neige"),
    230: ("❄️", "Blizzard"),
    248: ("🌫️", "Brouillard givrant"),
    260: ("🌫️", "Brouillard givrant"),
    263: ("🌦️", "Bruine légère"),
    266: ("🌦️", "Bruine"),
    281: ("🌧️", "Bruine verglaçante"),
    284: ("🌧️", "Bruine verglaçante épaisse"),
    293: ("🌦️", "Pluie légère"),
    296: ("🌧️", "Pluie légère"),
    299: ("🌧️", "Pluie modérée par intervalles"),
    302: ("🌧️", "Pluie modérée"),
    305: ("🌧️", "Pluie forte par intervalles"),
    308: ("🌧️", "Pluie forte"),
    311: ("🌧️", "Bruine verglaçante légère"),
    314: ("🌧️", "Bruine verglaçante modérée"),
    317: ("🌨️", "Pluie et neige mêlées"),
    320: ("🌨️", "Neige légère"),
    323: ("❄️", "Chutes de neige légères par intervalles"),
    326: ("❄️", "Chutes de neige légères"),
    329: ("❄️", "Chutes de neige modérées par intervalles"),
    332: ("❄️", "Chutes de neige modérées"),
    335: ("❄️", "Chutes de neige fortes par intervalles"),
    338: ("❄️", "Chutes de neige fortes"),
    350: ("🧊", "Grêle"),
    353: ("🌦️", "Averses légères"),
    356: ("🌧️", "Averses de pluie modérées"),
    359: ("🌧️", "Averses de pluie fortes"),
    362: ("🌨️", "Averses de neige légères"),
    365: ("🌨️", "Averses de neige modérées"),
    368: ("❄️", "Averses de neige légères"),
    371: ("❄️", "Averses de neige fortes"),
    374: ("🧊", "Averses de grêle légères"),
    377: ("🧊", "Averses de grêle modérées"),
    386: ("⛈️", "Pluie légère avec orage"),
    389: ("⛈️", "Pluie modérée avec orage"),
    392: ("⛈️", "Neige légère avec orage"),
    395: ("⛈️", "Neige modérée avec orage"),
}


def get_weather(location: str = LOCATION) -> dict:
    """Retourne la météo actuelle + prévisions du jour pour la localisation donnée."""
    try:
        url = f"https://wttr.in/{location.replace(' ', '+')}?format=j1"
        resp = requests.get(url, headers={"User-Agent": "Archimede-Bot/1.0"}, timeout=8)
        resp.raise_for_status()
        raw = resp.json()
        data = raw.get("data", raw)  # wttr.in enveloppe dans "data"

        current = data["current_condition"][0]
        today = data["weather"][0]

        temp_c = int(current["temp_C"])
        feels_like = int(current["FeelsLikeC"])
        humidity = int(current["humidity"])
        wind_kmph = int(current["windspeedKmph"])
        code = int(current["weatherCode"])
        emoji, description = WEATHER_CODES.get(code, ("🌡️", current.get("weatherDesc", [{}])[0].get("value", "?")))

        max_c = int(today["maxtempC"])
        min_c = int(today["mintempC"])

        # Prévisions par heure (matin / après-midi / soir)
        hours = today.get("hourly", [])
        morning = next((h for h in hours if int(h["time"]) >= 600), None)
        afternoon = next((h for h in hours if int(h["time"]) >= 1200), None)
        evening = next((h for h in hours if int(h["time"]) >= 1800), None)

        def hour_summary(h):
            if not h:
                return ""
            c = int(h["tempC"])
            code_h = int(h["weatherCode"])
            em, _ = WEATHER_CODES.get(code_h, ("🌡️", ""))
            return f"{em} {c}°C"

        summary = (
            f"{emoji} {description} · {temp_c}°C (ressenti {feels_like}°C)\n"
            f"Min {min_c}°C / Max {max_c}°C · Humidité {humidity}% · Vent {wind_kmph} km/h\n"
            f"Matin {hour_summary(morning)} · Après-midi {hour_summary(afternoon)} · Soir {hour_summary(evening)}"
        )

        return {
            "summary": summary,
            "emoji": emoji,
            "description": description,
            "temp_c": temp_c,
            "feels_like": feels_like,
            "max_c": max_c,
            "min_c": min_c,
            "humidity": humidity,
            "wind_kmph": wind_kmph,
            "outdoor_ok": code in [113, 116] and wind_kmph < 30,
        }

    except Exception as e:
        return {
            "summary": f"⚠️ Météo indisponible ({e})",
            "emoji": "⚠️",
            "description": "Indisponible",
            "outdoor_ok": None,
        }
