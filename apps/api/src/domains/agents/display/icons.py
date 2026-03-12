"""
Material Symbols Icon System - Centralized Icon Management.

Provides a unified icon system replacing emojis with Material Symbols
for a modern, consistent, and professional UI.

Usage:
    from src.domains.agents.display.icons import icon, Icons

    # Render an icon
    html = icon("mail")  # -> <span class="lia-icon"><span class="material-symbols-outlined">mail</span></span>

    # Use named constants
    html = icon(Icons.EMAIL)

    # With size variant
    html = icon("mail", size="lg")

    # With domain color
    html = icon("mail", domain="email")
"""

from __future__ import annotations

from typing import Literal

# =============================================================================
# Icon Name Constants
# =============================================================================


class Icons:
    """Material Symbols icon names used throughout the application."""

    # Communication
    EMAIL = "mail"
    PHONE = "phone"
    CHAT = "chat"
    FORWARD = "forward"
    REPLY = "reply"
    ARCHIVE = "archive"
    SEND = "send"
    MARK_EMAIL_UNREAD = "mark_email_unread"
    MARK_EMAIL_READ = "mark_email_read"
    OPEN_IN_NEW = "open_in_new"

    # People & Contacts
    PERSON = "person"
    GROUP = "group"
    MOOD = "sentiment_satisfied"  # smiley/nickname
    WORK = "work"  # occupation/job
    FAMILY = "family_restroom"  # generic family/relative
    CHILD = "child_care"  # child/son/daughter
    ELDERLY = "elderly"  # parent/older
    FAVORITE = "favorite"  # spouse/partner (heart)
    FAVORITE_BORDER = "favorite_border"  # partner (outline heart)
    HANDSHAKE = "handshake"  # friend
    SUPERVISOR = "supervisor_account"  # manager
    SUPPORT = "support_agent"  # assistant
    FACE_WOMAN = "face_3"  # mother/sister/daughter
    FACE_MAN = "face_6"  # father/brother/son
    LABEL = "label"  # for tags/labels

    # Location
    LOCATION = "location_on"
    DIRECTIONS = "directions"
    MAP = "map"
    PLACE = "place"
    DISTANCE = "straighten"

    # Routes / Navigation
    ROUTE = "route"
    NAVIGATION = "navigation"
    CAR = "directions_car"
    WALK = "directions_walk"
    BIKE = "directions_bike"
    TRANSIT = "directions_transit"
    MOTORCYCLE = "two_wheeler"
    TOLL = "toll"
    HIGHWAY = "add_road"
    FERRY = "directions_boat"
    TRAFFIC = "traffic"
    TIMER = "timer"
    FLAG_START = "flag"
    FLAG_END = "sports_score"

    # Calendar & Time
    CALENDAR = "calendar_month"
    EVENT = "event"
    DATE_RANGE = "date_range"
    SCHEDULE = "schedule"
    REMINDER = "notifications"
    ALARM = "alarm"

    # Tasks
    TASK = "task_alt"
    CHECKBOX = "check_box"
    CHECKBOX_BLANK = "check_box_outline_blank"
    CHECKLIST = "checklist"

    # Files & Documents
    FILE = "description"
    FOLDER = "folder"
    FOLDER_OPEN = "folder_open"
    ATTACHMENT = "attach_file"
    DOWNLOAD = "download"
    PDF = "picture_as_pdf"
    IMAGE = "image"
    VIDEO = "movie"
    AUDIO = "music_note"
    SPREADSHEET = "table_chart"
    PRESENTATION = "slideshow"
    CODE = "code"
    PACKAGE = "inventory_2"

    # Content
    EDIT = "edit"
    NOTE = "edit_note"
    DESCRIPTION = "description"
    TEXT = "notes"
    LINK = "link"

    # Personal Info
    BIRTHDAY = "cake"
    ANNIVERSARY = "favorite"
    SKILLS = "psychology"  # or "emoji_objects"
    INTERESTS = "lightbulb"

    # Weather
    SUNNY = "light_mode"
    CLOUDY = "cloud"
    PARTLY_CLOUDY = "partly_cloudy_day"
    RAINY = "rainy"
    SNOWY = "ac_unit"
    STORMY = "thunderstorm"
    WIND = "air"
    HUMIDITY = "water_drop"
    TEMPERATURE = "thermostat"
    SUNRISE = "wb_twilight"
    SUNSET = "nights_stay"
    PRESSURE = "speed"
    CLOUD_COVER = "filter_drama"

    # Ratings & Stars
    STAR = "star"
    STAR_HALF = "star_half"
    STAR_OUTLINE = "star_outline"

    # Actions
    OPEN = "open_in_new"
    SHARE = "share"
    DELETE = "delete"
    SETTINGS = "settings"
    MORE = "more_horiz"
    EXPAND = "expand_more"
    COLLAPSE = "expand_less"
    INFO = "info"
    HELP = "help"

    # Status
    CHECK = "check"
    CLOSE = "close"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "check_circle"

    # Video/Meeting
    VIDEO_CALL = "videocam"
    MEETING = "groups"

    # Search & Knowledge
    SEARCH = "search"
    ARTICLE = "article"
    WEB = "language"
    AI = "smart_toy"  # AI/robot icon for Perplexity
    BOOK = "menu_book"  # Book icon for Wikipedia
    EXTENSION = "extension"  # MCP/plugin icon (puzzle piece)

    # Payment & Accessibility
    CREDIT_CARD = "credit_card"
    PAYMENTS = "payments"
    ACCESSIBLE = "accessible"
    CONTACTLESS = "contactless"

    # Visibility
    VISIBILITY = "visibility"


# =============================================================================
# Emoji to Material Symbols Mapping
# =============================================================================

EMOJI_TO_ICON: dict[str, str] = {
    # Communication
    "📧": Icons.EMAIL,
    "✉️": Icons.EMAIL,
    "📱": Icons.PHONE,
    "☎️": Icons.PHONE,
    "💬": Icons.CHAT,
    "↩️": Icons.REPLY,
    "↪️": Icons.FORWARD,
    "📂": Icons.ARCHIVE,
    "📎": Icons.ATTACHMENT,
    # People
    "👤": Icons.PERSON,
    "👥": Icons.GROUP,
    "😊": Icons.MOOD,
    "👔": Icons.WORK,
    # Location & Routes
    "📍": Icons.LOCATION,
    "🗺️": Icons.MAP,
    "🚗": Icons.CAR,
    "🚶": Icons.WALK,
    "🚴": Icons.BIKE,
    "🚌": Icons.TRANSIT,
    "🏍️": Icons.MOTORCYCLE,
    # Calendar
    "📅": Icons.CALENDAR,
    "📆": Icons.DATE_RANGE,
    "🔔": Icons.REMINDER,
    # Tasks
    "✅": Icons.TASK,
    "☑️": Icons.CHECKBOX,
    "⬜": Icons.CHECKBOX_BLANK,
    # Personal
    "🎂": Icons.BIRTHDAY,
    "🎯": Icons.SKILLS,
    "💡": Icons.INTERESTS,
    "📝": Icons.NOTE,
    # Files
    "📄": Icons.PDF,
    "📃": Icons.FILE,
    "🖼️": Icons.IMAGE,
    "🎬": Icons.VIDEO,
    "🎵": Icons.AUDIO,
    "📊": Icons.SPREADSHEET,
    "📑": Icons.PRESENTATION,
    "📦": Icons.PACKAGE,
    "🐍": Icons.CODE,  # Python
    "📜": Icons.CODE,  # JavaScript
    "🌐": Icons.WEB,  # HTML
    "🎨": Icons.CODE,  # CSS
    "📋": Icons.CODE,  # JSON/XML
    # Weather
    "☀️": Icons.SUNNY,
    "🌤️": Icons.PARTLY_CLOUDY,
    "⛅": Icons.PARTLY_CLOUDY,
    "☁️": Icons.CLOUDY,
    "🌧️": Icons.RAINY,
    "🌦️": Icons.RAINY,
    "❄️": Icons.SNOWY,
    "🌨️": Icons.SNOWY,
    "⛈️": Icons.STORMY,
    "🌩️": Icons.STORMY,
    "💨": Icons.WIND,
    "💧": Icons.HUMIDITY,
    "🌡️": Icons.TEMPERATURE,
    # Ratings
    "⭐": Icons.STAR,
    "★": Icons.STAR,
    "☆": Icons.STAR_OUTLINE,
    # Video
    "📹": Icons.VIDEO_CALL,
    # Search/Web
    "🔍": Icons.SEARCH,
    "📰": Icons.ARTICLE,
}


# =============================================================================
# Attachment Type to Icon Mapping
# =============================================================================

ATTACHMENT_TYPE_ICONS: dict[str, tuple[str, str]] = {
    # (icon_name, css_class_suffix)
    "pdf": (Icons.PDF, "pdf"),
    "doc": (Icons.FILE, "doc"),
    "docx": (Icons.FILE, "doc"),
    "xls": (Icons.SPREADSHEET, "sheet"),
    "xlsx": (Icons.SPREADSHEET, "sheet"),
    "ppt": (Icons.PRESENTATION, "doc"),
    "pptx": (Icons.PRESENTATION, "doc"),
    "txt": (Icons.FILE, "doc"),
    "rtf": (Icons.FILE, "doc"),
    "csv": (Icons.SPREADSHEET, "sheet"),
    # Images
    "jpg": (Icons.IMAGE, "image"),
    "jpeg": (Icons.IMAGE, "image"),
    "png": (Icons.IMAGE, "image"),
    "gif": (Icons.IMAGE, "image"),
    "webp": (Icons.IMAGE, "image"),
    "svg": (Icons.IMAGE, "image"),
    "bmp": (Icons.IMAGE, "image"),
    # Videos
    "mp4": (Icons.VIDEO, "video"),
    "avi": (Icons.VIDEO, "video"),
    "mov": (Icons.VIDEO, "video"),
    "mkv": (Icons.VIDEO, "video"),
    "webm": (Icons.VIDEO, "video"),
    # Audio
    "mp3": (Icons.AUDIO, "audio"),
    "wav": (Icons.AUDIO, "audio"),
    "ogg": (Icons.AUDIO, "audio"),
    "flac": (Icons.AUDIO, "audio"),
    "m4a": (Icons.AUDIO, "audio"),
    # Archives
    "zip": (Icons.PACKAGE, "archive"),
    "rar": (Icons.PACKAGE, "archive"),
    "7z": (Icons.PACKAGE, "archive"),
    "tar": (Icons.PACKAGE, "archive"),
    "gz": (Icons.PACKAGE, "archive"),
    # Code
    "py": (Icons.CODE, "code"),
    "js": (Icons.CODE, "code"),
    "ts": (Icons.CODE, "code"),
    "html": (Icons.WEB, "code"),
    "css": (Icons.CODE, "code"),
    "json": (Icons.CODE, "code"),
    "xml": (Icons.CODE, "code"),
    # Default
    "default": (Icons.ATTACHMENT, "default"),
}


# =============================================================================
# Weather Condition to Icon Mapping
# =============================================================================

WEATHER_ICONS: dict[str, str] = {
    "clear": Icons.SUNNY,
    "sunny": Icons.SUNNY,
    "sun": Icons.SUNNY,
    "partly_cloudy": Icons.PARTLY_CLOUDY,
    "partly cloudy": Icons.PARTLY_CLOUDY,
    "cloudy": Icons.CLOUDY,
    "cloud": Icons.CLOUDY,
    "overcast": Icons.CLOUDY,
    "rain": Icons.RAINY,
    "rainy": Icons.RAINY,
    "drizzle": Icons.RAINY,
    "showers": Icons.RAINY,
    "snow": Icons.SNOWY,
    "snowy": Icons.SNOWY,
    "sleet": Icons.SNOWY,
    "storm": Icons.STORMY,
    "stormy": Icons.STORMY,
    "thunderstorm": Icons.STORMY,
    "thunder": Icons.STORMY,
    "wind": Icons.WIND,
    "windy": Icons.WIND,
    "default": Icons.CLOUDY,
}


# =============================================================================
# Relation Type to Icon Mapping (Google Contacts API relation types)
# =============================================================================

RELATION_TYPE_ICONS: dict[str, str] = {
    # Romantic relationships
    "spouse": Icons.FAVORITE,
    "partner": Icons.FAVORITE_BORDER,
    "domesticpartner": Icons.FAVORITE_BORDER,
    # Parent relationships
    "parent": Icons.ELDERLY,
    "mother": Icons.FACE_WOMAN,
    "father": Icons.FACE_MAN,
    # Child relationships
    "child": Icons.CHILD,
    "son": Icons.CHILD,
    "daughter": Icons.CHILD,
    # Sibling relationships
    "sibling": Icons.GROUP,
    "brother": Icons.FACE_MAN,
    "sister": Icons.FACE_WOMAN,
    # Extended family
    "relative": Icons.FAMILY,
    # Professional relationships
    "friend": Icons.HANDSHAKE,
    "manager": Icons.SUPERVISOR,
    "assistant": Icons.SUPPORT,
    # Default fallback
    "default": Icons.GROUP,
}


# =============================================================================
# Icon Rendering Functions
# =============================================================================

IconSize = Literal["xs", "sm", "md", "lg", "xl"]
IconDomain = Literal["email", "contact", "calendar", "drive", "task", "place", "weather", "route"]
IconColor = Literal["white", "inherit", "muted"]


def icon(
    name: str,
    size: IconSize | None = None,
    domain: IconDomain | None = None,
    filled: bool = False,
    aria_label: str | None = None,
    color: IconColor | None = None,
) -> str:
    """
    Render a Material Symbols icon with proper styling.

    Args:
        name: Icon name (e.g., "mail", "phone", Icons.EMAIL)
        size: Size variant (xs, sm, md, lg, xl)
        domain: Domain color (email, contact, calendar, etc.)
        filled: If True, use filled style instead of outlined
        aria_label: Accessibility label (icon is decorative if None)
        color: Force icon color (white, inherit, muted)

    Returns:
        HTML string for the icon

    Example:
        icon("mail")  # Default
        icon(Icons.PHONE, size="lg", domain="contact")
        icon("star", filled=True)
        icon(Icons.CAR, size="sm", color="white")  # White icon for badges
    """
    # Build CSS classes
    classes = ["lia-icon"]

    if size:
        classes.append(f"lia-icon--{size}")

    if domain:
        classes.append(f"lia-icon--{domain}")

    if filled:
        classes.append("lia-icon--filled")

    if color:
        classes.append(f"lia-icon--{color}")

    class_str = " ".join(classes)

    # Accessibility
    aria_attr = f' aria-label="{aria_label}"' if aria_label else ' aria-hidden="true"'

    return (
        f'<span class="{class_str}"{aria_attr}>'
        f'<span class="material-symbols-outlined">{name}</span>'
        f"</span>"
    )


def icon_for_action_button(name: str) -> str:
    """
    Render an icon specifically for action buttons.

    Uses the lia-action-btn__icon wrapper for proper sizing.

    Args:
        name: Icon name

    Returns:
        HTML string for the action button icon
    """
    return (
        f'<span class="lia-action-btn__icon" aria-hidden="true">'
        f'<span class="material-symbols-outlined">{name}</span>'
        f"</span>"
    )


def get_icon_for_emoji(emoji: str) -> str:
    """
    Get the Material Symbols icon name for a given emoji.

    Falls back to a sensible default if emoji not found.

    Args:
        emoji: Emoji character

    Returns:
        Material Symbols icon name
    """
    return EMOJI_TO_ICON.get(emoji, Icons.INFO)


def get_attachment_icon(
    filename: str | None = None,
    mime_type: str | None = None,
) -> tuple[str, str]:
    """
    Get attachment icon and CSS class from filename or MIME type.

    Args:
        filename: File name with extension
        mime_type: MIME type string

    Returns:
        Tuple of (icon_name, css_class_suffix)
    """
    # Try filename extension first
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in ATTACHMENT_TYPE_ICONS:
            return ATTACHMENT_TYPE_ICONS[ext]

    # Try MIME type
    if mime_type:
        mime_lower = mime_type.lower()
        if "pdf" in mime_lower:
            return ATTACHMENT_TYPE_ICONS["pdf"]
        elif "word" in mime_lower or "document" in mime_lower:
            return ATTACHMENT_TYPE_ICONS["doc"]
        elif "sheet" in mime_lower or "excel" in mime_lower:
            return ATTACHMENT_TYPE_ICONS["xlsx"]
        elif "presentation" in mime_lower or "powerpoint" in mime_lower:
            return ATTACHMENT_TYPE_ICONS["pptx"]
        elif mime_lower.startswith("image/"):
            return ATTACHMENT_TYPE_ICONS["png"]
        elif mime_lower.startswith("video/"):
            return ATTACHMENT_TYPE_ICONS["mp4"]
        elif mime_lower.startswith("audio/"):
            return ATTACHMENT_TYPE_ICONS["mp3"]
        elif "zip" in mime_lower or "archive" in mime_lower or "compressed" in mime_lower:
            return ATTACHMENT_TYPE_ICONS["zip"]

    return ATTACHMENT_TYPE_ICONS["default"]


def get_weather_icon(condition: str) -> str:
    """
    Get the weather icon for a given condition.

    Args:
        condition: Weather condition string

    Returns:
        Material Symbols icon name
    """
    condition_lower = condition.lower().strip()

    # Try direct match
    if condition_lower in WEATHER_ICONS:
        return WEATHER_ICONS[condition_lower]

    # Try partial match
    for key, icon_name in WEATHER_ICONS.items():
        if key in condition_lower:
            return icon_name

    return WEATHER_ICONS["default"]


def get_relation_icon(relation_type: str) -> str:
    """
    Get the icon for a given relation type.

    Args:
        relation_type: Relation type from Google Contacts API
            (e.g., 'spouse', 'child', 'parent', 'friend', 'manager')

    Returns:
        Material Symbols icon name
    """
    if not relation_type:
        return RELATION_TYPE_ICONS["default"]

    type_lower = relation_type.lower().strip()

    # Try direct match
    if type_lower in RELATION_TYPE_ICONS:
        return RELATION_TYPE_ICONS[type_lower]

    # Try without spaces (e.g., "domestic partner" -> "domesticpartner")
    type_no_spaces = type_lower.replace(" ", "").replace("_", "")
    if type_no_spaces in RELATION_TYPE_ICONS:
        return RELATION_TYPE_ICONS[type_no_spaces]

    return RELATION_TYPE_ICONS["default"]


def render_star_rating(rating: float | None, max_stars: int = 5) -> str:
    """
    Generate star rating HTML with Material Symbols.

    Args:
        rating: Rating value (e.g., 4.5)
        max_stars: Maximum stars to display

    Returns:
        HTML string for star rating
    """
    if rating is None:
        return ""

    full = int(rating)
    half = 1 if rating - full >= 0.5 else 0
    empty = max_stars - full - half

    parts = ['<span class="lia-rating">']

    # Full stars
    for _ in range(full):
        parts.append(
            f'<span class="lia-rating__star--full">'
            f'<span class="material-symbols-outlined">{Icons.STAR}</span>'
            f"</span>"
        )

    # Half star
    if half:
        parts.append(
            f'<span class="lia-rating__star--half">'
            f'<span class="material-symbols-outlined">{Icons.STAR_HALF}</span>'
            f"</span>"
        )

    # Empty stars
    for _ in range(empty):
        parts.append(
            f'<span class="lia-rating__star--empty">'
            f'<span class="material-symbols-outlined">{Icons.STAR_OUTLINE}</span>'
            f"</span>"
        )

    parts.append(f'<span class="lia-rating__value">{rating}</span>')
    parts.append("</span>")

    return "".join(parts)


# =============================================================================
# Travel Mode to Icon Mapping (Google Routes API)
# =============================================================================

TRAVEL_MODE_ICONS: dict[str, str] = {
    # API values (uppercase)
    "DRIVE": Icons.CAR,
    "WALK": Icons.WALK,
    "BICYCLE": Icons.BIKE,
    "TRANSIT": Icons.TRANSIT,
    "TWO_WHEELER": Icons.MOTORCYCLE,
}


def get_travel_mode_icon(travel_mode: str) -> str:
    """
    Get the Material Symbols icon for a travel mode.

    Args:
        travel_mode: Travel mode from Google Routes API
            (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)

    Returns:
        Material Symbols icon name
    """
    return TRAVEL_MODE_ICONS.get(travel_mode.upper() if travel_mode else "DRIVE", Icons.CAR)
