import re
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber
from icalendar import Calendar, Event


# ============================================================
# CONFIGURACIÓN
# ============================================================

PDF_FILE = "calendari.pdf"
OUTPUT_FILE = "calendar.ics"

TEAM_ID = "88834"

TEAM_NAME = "A.E. BADALONÈS"

CALENDAR_NAME = "🏀 A.E. Badalonès - Senior B"

CATEGORY = "1A. TERRITORIAL SÈNIOR MASCULÍ"

SOURCE_URL = (
    "https://www.basquetcatala.cat/"
    "partits/calendari_equip_global/pdf/88834"
)

LOCAL_TZ = ZoneInfo("Europe/Madrid")

# Reserva 2 horas para cada partido
GAME_DURATION_MINUTES = 120


# ============================================================
# TEXTO
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def extract_lines_from_pdf(pdf_file):
    lines = []

    with pdfplumber.open(pdf_file) as pdf:

        for page in pdf.pages:

            text = page.extract_text()

            if not text:
                continue

            for line in text.splitlines():

                line = clean_text(line)

                if line:
                    lines.append(line)

    return lines


# ============================================================
# FECHA
# ============================================================

def parse_datetime(line):

    pattern = (
        r"^(\d{2}-\d{2}-\d{4})"
        r"\s+"
        r"(\d{2}:\d{2})"
    )

    match = re.match(pattern, line)

    if not match:
        return None

    date_text = match.group(1)
    time_text = match.group(2)

    dt = datetime.strptime(
        f"{date_text} {time_text}",
        "%d-%m-%Y %H:%M"
    )

    return dt.replace(tzinfo=LOCAL_TZ)


def remove_datetime(line):

    return re.sub(
        r"^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}\s+",
        "",
        line
    ).strip()


# ============================================================
# PARTIDO
# ============================================================

def remove_category(text):

    return clean_text(
        text.replace(CATEGORY, "")
    )


def split_teams(match_text):

    """
    El equipo A.E. BADALONÈS aparece siempre completo.

    Ejemplo local:

    A.E. BADALONÈS - PINTURAS CORBACHO - MEDIBAIX - CB GAVÀ

    Ejemplo visitante:

    ESCOLAPIS SARRIÀ B - A.E. BADALONÈS - PINTURAS CORBACHO
    """

    match_text = clean_text(match_text)

    if match_text.startswith(TEAM_NAME):

        opponent = match_text[len(TEAM_NAME):]

        opponent = re.sub(
            r"^\s*-\s*",
            "",
            opponent
        )

        return {
            "home": TEAM_NAME,
            "away": clean_text(opponent),
            "is_home": True
        }

    if match_text.endswith(TEAM_NAME):

        opponent = match_text[:-len(TEAM_NAME)]

        opponent = re.sub(
            r"\s*-\s*$",
            "",
            opponent
        )

        return {
            "home": clean_text(opponent),
            "away": TEAM_NAME,
            "is_home": False
        }

    return {
        "home": "",
        "away": "",
        "is_home": False
    }


# ============================================================
# PABELLÓN
# ============================================================

def parse_location(line):

    location = line.replace(
        "Instal·lació:",
        "",
        1
    ).strip()

    return clean_text(location)


# ============================================================
# UID
# ============================================================

def make_uid(home, away):

    """
    UID estable.

    NO incluimos fecha ni hora.

    Si la federación cambia el partido:
    sábado 19:30 -> domingo 17:45

    seguirá siendo el mismo evento.
    """

    identity = (
        f"{TEAM_ID}|"
        f"{home.lower()}|"
        f"{away.lower()}"
    )

    digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]

    return (
        f"{digest}"
        f"@basquetcalendar-{TEAM_ID}"
    )


# ============================================================
# LEER PARTIDOS
# ============================================================

def parse_games(lines):

    games = []

    current_game = None

    for line in lines:

        # Ignorar encabezados
        if line in [
            "Calendari Global Equip",
            "ASSOCIACIO ESPORTIVA BADALONES",
            "Data i hora Partit Categoria"
        ]:
            continue

        # Ignorar pie de página
        if line.startswith("Pàgina"):
            continue

        # ------------------------------
        # PARTIDO
        # ------------------------------

        dt = parse_datetime(line)

        if dt:

            match_text = remove_datetime(line)

            match_text = remove_category(
                match_text
            )

            teams = split_teams(
                match_text
            )

            current_game = {
                "datetime": dt,
                "home": teams["home"],
                "away": teams["away"],
                "is_home": teams["is_home"],
                "location": "",
                "category": CATEGORY
            }

            games.append(current_game)

            continue

        # ------------------------------
        # INSTALACIÓN
        # ------------------------------

        if (
            line.startswith("Instal·lació:")
            and current_game
        ):

            current_game["location"] = (
                parse_location(line)
            )

    return games


# ============================================================
# CALENDARIO
# ============================================================

def create_calendar(games):

    cal = Calendar()

    cal.add(
        "prodid",
        "-//AE Badalones Basketball Calendar//ES"
    )

    cal.add("version", "2.0")

    cal.add(
        "calscale",
        "GREGORIAN"
    )

    cal.add(
        "method",
        "PUBLISH"
    )

    cal.add(
        "x-wr-calname",
        CALENDAR_NAME
    )

    cal.add(
        "x-wr-timezone",
        "Europe/Madrid"
    )

    for game in games:

        event = Event()

        start = game["datetime"]

        end = start + timedelta(
            minutes=GAME_DURATION_MINUTES
        )

        # ------------------------------
        # TÍTULO
        # ------------------------------

        if game["is_home"]:

            summary = (
                f"🏀 vs {game['away']} 🏠"
            )

        else:

            summary = (
                f"🏀 @ {game['home']} ✈️"
            )

        # ------------------------------
        # UID
        # ------------------------------

        event.add(
            "uid",
            make_uid(
                game["home"],
                game["away"]
            )
        )

        # ------------------------------
        # EVENTO
        # ------------------------------

        event.add(
            "summary",
            summary
        )

        event.add(
            "dtstart",
            start
        )

        event.add(
            "dtend",
            end
        )

        event.add(
            "dtstamp",
            datetime.now(timezone.utc)
        )

        # ------------------------------
        # LOCATION
        # ------------------------------

        if game["location"]:

            event.add(
                "location",
                game["location"]
            )

        # ------------------------------
        # DESCRIPTION
        # ------------------------------

        home_away = (
            "Local 🏠"
            if game["is_home"]
            else "Visitant ✈️"
        )

        description = (
            f"{game['home']} - {game['away']}\n\n"
            f"🏆 {game['category']}\n"
            f"🏀 {home_away}\n\n"
            f"Font oficial:\n"
            f"{SOURCE_URL}"
        )

        event.add(
            "description",
            description
        )

        event.add(
            "url",
            SOURCE_URL
        )

        cal.add_component(
            event
        )

    Path(OUTPUT_FILE).write_bytes(
        cal.to_ical()
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not Path(PDF_FILE).exists():

        raise FileNotFoundError(
            f"No s'ha trobat {PDF_FILE}"
        )

    lines = extract_lines_from_pdf(
        PDF_FILE
    )

    games = parse_games(
        lines
    )

    print("")
    print(
        f"Partits detectats: "
        f"{len(games)}"
    )
    print("")

    for i, game in enumerate(
        games,
        start=1
    ):

        print(
            f"{i:02d}. "
            f"{game['datetime']:%d-%m-%Y %H:%M}"
        )

        print(
            f"    {game['home']}"
        )

        print(
            f"    vs"
        )

        print(
            f"    {game['away']}"
        )

        print(
            f"    📍 {game['location']}"
        )

        print("")

    create_calendar(
        games
    )

    print(
        f"✅ Calendari creat: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
