"""D2 — the semantic type of a value, given where it appears (every concrete type of the registry).

For each concrete type: two calibration cases then two independent cases. Values
are the author's own (the registry's illustrative ``examples`` are never reused,
except where the type's vocabulary IS its value set, e.g. task statuses). Values
of internal vocabularies come from the code that emits them (2026-10-11 census).
``also`` lists other types an informed reader would accept for the same value
and context; ancestors of the gold type count in lenient scoring only.
"""

from scripts.jev_semantic.cases import Case, Split, single

# type -> four (value, context, also) cases: [cal, cal, ind, ind]
C = tuple[str, str, tuple[str, ...]]
CASES: dict[str, tuple[C, C, C, C]] = {
    # ---------------------------------------------------------------- IDENTITY
    "email_address": (
        ("lea.fontaine@example.test", "Recipient field of an email draft", ()),
        ("support@acme-industries.example", "Contact address listed on a company website", ()),
        ("j.okafor@uni-lagos.example", "The 'to' list of a meeting invitation", ()),
        ("ventas@tienda-sol.example", "Address copied from a shop's footer", ()),
    ),
    "phone_number": (
        ("+33 6 45 12 78 90", "Mobile number on a contact card", ()),
        ("01 43 22 19 08", "Phone of a restaurant in Paris search results", ()),
        ("+49 30 1234567", "Number to call for a hotel booking", ()),
        ("(415) 555-0188", "Callback number left in a voicemail transcript", ()),
    ),
    "person_name": (
        ("Hélène Marchand", "Name of an attendee of a calendar event", ()),
        ("Yuki Tanaka", "Author of an email", ()),
        ("Ibrahim Diallo", "Display name of an address book entry", ()),
        ("María José Herrera", "Person mentioned as the guest of honour", ()),
    ),
    "organization_name": (
        ("Société Générale", "Employer field of a contact card", ()),
        ("Greenpeace", "Sender organisation of a newsletter", ()),
        ("Mairie de Lyon", "Organisation that issued a document", ()),
        ("Siemens Healthineers", "Company of a LinkedIn contact", ()),
    ),
    # ---------------------------------------------------------------- LOCATION
    "physical_address": (
        (
            "18 rue de la République, 13001 Marseille",
            "Destination of a route request",
            ("formatted_address",),
        ),
        ("Bahnhofstraße 7, 8001 Zürich", "Where to deliver a parcel", ("formatted_address",)),
        ("4 Privet Drive, Little Whinging", "Home address of a contact", ("formatted_address",)),
        ("Calle Mayor 22, 28013 Madrid", "Location of a calendar event", ("formatted_address",)),
    ),
    "formatted_address": (
        (
            "10 Downing St, London SW1A 2AA, UK",
            "Address string returned by the geocoding API for a place",
            ("physical_address",),
        ),
        (
            "Pl. du Capitole, 31000 Toulouse, France",
            "formattedAddress field of a place search result",
            ("physical_address",),
        ),
        (
            "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
            "Normalized address of a business in search results",
            ("physical_address",),
        ),
        (
            "Via del Corso, 00186 Roma RM, Italia",
            "Formatted address returned with a place's details",
            ("physical_address",),
        ),
    ),
    "coordinate": (
        ("45.7640, 4.8357", "Latitude and longitude pair of a meeting point", ("waypoint",)),
        ("(51.5074, -0.1278)", "Position shared from a phone", ("waypoint",)),
        ("-33.8688, 151.2093", "GPS fix of a photo", ("waypoint",)),
        ("40.4168,-3.7038", "Geographic position of a delivery", ("waypoint",)),
    ),
    "country_code": (
        ("FR", "Country of a postal address, as a two-letter ISO code", ()),
        ("JP", "regionCode returned for a place", ()),
        ("DE", "Country filter of a search, as an ISO 3166 code", ("language_code",)),
        ("BR", "Two-letter country of a phone number's origin", ()),
    ),
    "postal_code": (
        ("75011", "ZIP/postal code of an address", ()),
        ("SW1A 1AA", "Postcode of a UK address", ()),
        ("80331", "Postleitzahl of an address in Munich", ()),
        ("10001", "ZIP code of a New York address", ()),
    ),
    "locality": (
        ("Montreuil", "City where the user wants the weather", ("area_name",)),
        ("Lyon", "Town of a contact's address", ("area_name",)),
        ("Sevilla", "City name for a hotel search", ("area_name",)),
        ("Kyoto", "City of a trip destination", ("area_name",)),
    ),
    "area_name": (
        ("Île-de-France", "Region covered by a weather alert", ("locality",)),
        ("Le Marais", "Neighbourhood to search restaurants in", ("locality",)),
        ("Bavaria", "Region of a travel itinerary", ("locality",)),
        ("Shoreditch", "District of London for a bar search", ("locality",)),
    ),
    "waypoint": (
        (
            "Dijon",
            "Intermediate stop on a drive from Paris to Lyon",
            ("locality", "physical_address"),
        ),
        ("Aire de Beaune-Tailly", "Rest stop to pass through on a route", ("physical_address",)),
        ("Chamonix", "Via point added between Geneva and Turin", ("locality", "physical_address")),
        ("Gare de Valence TGV", "Intermediate point to pass by on a trip", ("physical_address",)),
    ),
    "latitude": (
        ("48.8584", "Latitude of a place in decimal degrees", ()),
        ("-23.5505", "Latitude component of a location", ()),
        ("43.2965", "North-south coordinate of a beach in decimal degrees", ()),
        ("59.3293", "Latitude returned for a city centre", ()),
    ),
    "longitude": (
        ("2.2945", "Longitude of a place in decimal degrees", ()),
        ("-46.6333", "Longitude component of a location", ()),
        ("5.3698", "East-west coordinate of a beach in decimal degrees", ()),
        ("18.0686", "Longitude returned for a city centre", ()),
    ),
    "polyline": (
        ("_p~iF~ps|U_ulLnnqC_mqNvxq`@", "Encoded path of a route returned by the routing API", ()),
        ("a~l~Fjk~uOwHJy@P", "Compressed geometry of a walking route", ()),
        ("gfo}EtohhUxD@bAxJmGF", "Encoded overview path of a driving route", ()),
        ("mkm_IqzsMcBhDkCvB", "Path string to draw a bike route on a map", ()),
    ),
    # ------------------------------------------------------------- MEASUREMENT
    "radius_meters": (
        ("1500", "Search radius around the user's position, in meters", ("distance",)),
        ("500", "Radius of a nearby cafe search, in meters", ("distance",)),
        ("3000", "Maximum distance from the hotel for a search, in meters", ("distance",)),
        ("800", "Radius parameter of a nearby pharmacy search, in meters", ("distance",)),
    ),
    "distance": (
        ("12.4 km", "Length of a driving route", ()),
        ("850 m", "Distance between the station and the hotel", ()),
        ("3.2 miles", "Length of a running route", ()),
        ("462 km", "Road distance from Paris to Lyon", ()),
    ),
    "temperature": (
        ("18 °C", "Afternoon value in a weather forecast", ()),
        ("-4°C", "Minimum of the night in a forecast", ()),
        ("72°F", "Current reading in a weather report", ()),
        ("31.5 °C", "Maximum of the day in a heatwave bulletin", ()),
    ),
    "humidity": (
        ("76%", "Relative humidity in a weather forecast", ("precipitation_probability",)),
        ("45 %", "Air humidity of the current conditions", ()),
        ("90%", "Humidity level of a foggy morning", ()),
        ("62 %", "Average humidity of the day", ()),
    ),
    "wind_speed": (
        ("2.4 m/s", "Wind in the current weather conditions", ()),
        ("35 km/h", "Gusts in a storm warning", ()),
        ("12 mph", "Wind of a sailing forecast", ()),
        ("18 km/h", "Average wind of the day", ()),
    ),
    "precipitation_probability": (
        ("60%", "Chance of rain in the afternoon forecast", ("humidity",)),
        ("10 %", "Probability of precipitation tomorrow", ()),
        ("85%", "Chance of showers during the hike", ()),
        ("0 %", "Risk of rain for the evening", ()),
    ),
    "rating": (
        ("4.6", "Average review score of a restaurant out of 5", ("confidence_score",)),
        ("3.9/5", "Customer rating of a hotel", ()),
        ("4.8", "Stars of a bakery in search results", ()),
        ("2.7", "User score of a bar out of 5", ()),
    ),
    "file_size": (
        ("2457600", "Size of a Drive file in bytes", ()),
        ("18.3 MB", "Attachment size of an email", ()),
        ("512 KB", "Size of an uploaded image", ()),
        ("104857600", "Byte size of a video file", ()),
    ),
    "confidence_score": (
        ("0.87", "Score of a classification between 0 and 1", ("rating",)),
        ("0.42", "How sure an extraction is, from 0 to 1", ()),
        ("0.995", "Match certainty of an entity resolution", ()),
        ("0.61", "Relevance confidence returned with a search hit", ()),
    ),
    # --------------------------------------------------------------- TEMPORAL
    "Date": (
        ("2026-11-03", "Day of a planned trip", ()),
        ("2027-01-15", "Due date of a task", ()),
        ("2026-12-24", "Day to check the weather for", ()),
        ("2026-10-30", "Deadline day of a project", ()),
    ),
    "unix_timestamp": (
        ("1791763200", "dt field of a forecast entry (seconds since epoch)", ()),
        ("1767225600", "Epoch seconds of an event in a log", ()),
        ("1790000000", "Time of a sensor reading, as seconds since 1970", ()),
        ("1800000000", "Expiry time in seconds since the epoch", ()),
    ),
    "duration_minutes": (
        ("45", "Length of a meeting slot, in minutes", ()),
        ("90", "Travel time in minutes", ()),
        ("30", "Requested free slot length in minutes", ()),
        ("135", "Driving time of a route, in minutes", ()),
    ),
    "datetime": (
        ("2026-10-14T09:30:00+02:00", "When a document was shared", ()),
        ("2026-11-02T18:00:00Z", "Timestamp mentioned in a notification", ()),
        ("2026-12-01T07:15:00+01:00", "Moment the train departs", ()),
        ("2027-02-10T13:45:00-05:00", "Time a package was delivered", ()),
    ),
    "timezone": (
        ("Europe/Paris", "Time zone of the user's calendar", ()),
        ("America/Los_Angeles", "Zone of a meeting organiser", ()),
        ("Asia/Tokyo", "IANA zone of a travel destination", ()),
        ("Australia/Sydney", "Timezone of a colleague", ()),
    ),
    "duration": (
        ("PT1H30M", "Length of an activity as an ISO 8601 duration", ()),
        ("P2D", "Duration of a trip in ISO 8601 notation", ()),
        ("PT45M", "Duration field written in ISO 8601", ()),
        ("P1W", "ISO 8601 duration of a subscription trial", ()),
    ),
    "modification_timestamp": (
        ("2026-10-09T16:42:11.000Z", "modifiedTime of a Drive file", ("datetime",)),
        ("2026-09-30T08:05:00Z", "Last update time of a contact", ("datetime",)),
        ("2026-10-10T21:17:33.512Z", "When a document was last edited", ("datetime",)),
        ("2026-08-14T11:00:00Z", "updated field of a task", ("datetime",)),
    ),
    "birthday": (
        ("1987-04-22", "Birthday on a contact card", ("Date",)),
        ("03-15", "Birthday (month-day) of a friend", ("Date",)),
        ("1992-11-08", "Date of birth of a colleague", ("Date",)),
        ("2015-05-03", "Son's birthday", ("Date",)),
    ),
    "recency_filter": (
        ("week", "How recent web search results must be", ()),
        ("pm", "Freshness filter of a news search", ()),
        ("day", "Only results from the last day", ()),
        ("py", "Time window filter of a web search (past year)", ()),
    ),
    "formatted_time": (
        ("2h 30min", "Human-readable travel time of a route", ("duration_minutes",)),
        ("14h30", "Displayed time of an appointment", ()),
        ("3:45 PM", "Time shown to the user for a reminder", ()),
        ("1 h 05", "Displayed duration of a train trip", ("duration_minutes",)),
    ),
    "trigger_datetime": (
        ("2026-10-15T08:00:00+02:00", "When a reminder must fire", ("datetime",)),
        ("2026-11-01T19:30:00+01:00", "Time the alarm of a reminder goes off", ("datetime",)),
        ("2026-10-20T07:00:00+02:00", "Reminder trigger time", ("datetime",)),
        ("2026-12-31T23:00:00+01:00", "When to notify the user about a reminder", ("datetime",)),
    ),
    "event_start_datetime": (
        ("2026-10-16T10:00:00+02:00", "Start of a calendar meeting", ("datetime",)),
        ("2026-11-04T14:30:00+01:00", "When the dentist appointment begins", ("datetime",)),
        ("2026-10-22T09:00:00+02:00", "Start time of a workshop in the calendar", ("datetime",)),
        ("2026-12-05T20:00:00+01:00", "Beginning of a concert event", ("datetime",)),
    ),
    # ------------------------------------------------------------ RESOURCE_ID
    "event_id": (
        ("5k2m9qv0b7h3t1r8s4n6p0c2d1", "id of a Google Calendar event", ()),
        ("AAMkAGI2THVSAAA=", "id of an Outlook calendar event", ("message_id",)),
        ("0l8u3ce1n9g6v2j7b4x5a2m1qk", "Identifier of a meeting to update", ()),
        ("7fj3k9s2l0p1q8r4t6v5w3x2yz_20261015T080000Z", "Recurring event instance id", ()),
    ),
    "calendar_id": (
        ("primary", "Which calendar to list events from", ()),
        (
            "c_8f3a1e2d9b@group.calendar.google.com",
            "Calendar of a shared team agenda",
            ("email_address",),
        ),
        (
            "famille.lemoine@group.calendar.google.com",
            "Identifier of the family calendar",
            ("email_address",),
        ),
        (
            "en.french#holiday@group.v.calendar.google.com",
            "Calendar of public holidays",
            ("email_address",),
        ),
    ),
    "contact_id": (
        ("people/c4728193650012345678", "resourceName of an address book entry", ()),
        ("people/c1100293847561029384", "Identifier of a contact to update", ()),
        ("people/c9988776655443322110", "Which contact to delete", ()),
        ("people/c5647382910564738291", "Contact resource of a person", ()),
    ),
    "file_id": (
        ("1a2B3c4D5e6F7g8H9i0J_kLmNoPqRsTuV", "id of a Drive document", ("folder_id",)),
        ("1Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk2Ji1Hg0Fe", "File to download from Drive", ("folder_id",)),
        (
            "1QwErTyUiOpAsDfGhJkLzXcVbNm123456",
            "Identifier of a spreadsheet in Drive",
            ("folder_id",),
        ),
        ("1pLmOkNjIbHuVgYcFtXdRzEsWaQ098765", "Drive resource of a shared PDF", ("folder_id",)),
    ),
    "folder_id": (
        ("0B7xYzAbCdEfGhIjKlMnOpQrStU", "Parent folder of a Drive file", ("file_id",)),
        ("root", "Folder to list Drive files from", ()),
        ("1FoLdErIdExAmPlE_aBcDeFgHiJkLmNo", "Drive folder to move a file into", ("file_id",)),
        ("0AbCdEfGhIjKlUk9PVA", "Shared drive folder identifier", ("file_id",)),
    ),
    "message_id": (
        ("18f3a2b4c5d6e7f8", "id of a Gmail message", ("thread_id",)),
        ("AAMkADExNzIxYjEzLWFmZjYtNDA5Yi05", "id of an Outlook email", ("event_id",)),
        ("19a0b1c2d3e4f506", "Which email to reply to", ("thread_id",)),
        ("1928374655aabbcc", "Message to forward", ("thread_id",)),
    ),
    "thread_id": (
        ("18f3a2b4c5d6e000", "threadId of a Gmail conversation", ("message_id",)),
        ("19b2c3d4e5f60718", "Conversation to read in Gmail", ("message_id",)),
        ("17aa88bb99cc00dd", "Email thread to archive", ("message_id",)),
        ("1876ff54ee32dd10", "threadId of a discussion", ("message_id",)),
    ),
    "task_id": (
        ("MTIzNDU2Nzg5MDEyMzQ1Njc4OTA6MDoxMjM0", "id of a Google Tasks item", ("task_list_id",)),
        ("AQMkADAwATM0MDAAMS0zZmRhLTQ1ZTQt", "id of a Microsoft To Do task", ()),
        ("dGFza18xMjM0NTY3ODkwX2FiY2RlZg", "Task to mark as completed", ("task_list_id",)),
        ("OTg3NjU0MzIxMDk4NzY1NDMyMTA6MDo5", "Identifier of a to-do item", ("task_list_id",)),
    ),
    "task_list_id": (
        ("MDIwMjE0MTk3NDQ0ODQ5MDE0NjA6MDow", "id of a Google Tasks list", ("task_id",)),
        ("@default", "Which task list to read", ()),
        ("bGlzdF9jb3Vyc2VzXzIwMjY", "Task list of the groceries", ("task_id",)),
        ("MTAxMDEwMTAxMDEwMTAxMDE6MDow", "List to add the task to", ("task_id",)),
    ),
    "place_id": (
        ("ChIJD7fiBh9u5kcRYJSMaMOCCwQ", "id of a place in Google Places results", ()),
        ("ChIJ3S-JXmauEmsRUcIaWtf4MzE", "Place to fetch details for", ()),
        ("ChIJLU7jZClu5kcR4PcOOO6p3I0", "Google place identifier of a monument", ()),
        ("ChIJ5TCOcRaYpBIRCmZHTz37sEQ", "Place of a restaurant to get reviews for", ()),
    ),
    "reminder_id": (
        (
            "6f1c2d3e-4a5b-4c7d-8e9f-0a1b2c3d4e5f",
            "id of a reminder to cancel",
            ("ticket_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "a8b7c6d5-e4f3-4a2b-9c1d-0e9f8a7b6c5d",
            "Reminder to postpone",
            ("ticket_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "0f9e8d7c-6b5a-4f3e-8d2c-1b0a9f8e7d6c",
            "Which reminder to delete",
            ("ticket_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "5e4d3c2b-1a0f-4e9d-8c7b-6a5f4e3d2c1b",
            "Reminder identifier to update",
            ("ticket_id", "incident_id", "automation_id", "hue_light_id"),
        ),
    ),
    "wikipedia_page_id": (
        ("681159", "pageid of a Wikipedia article", ()),
        ("5042916", "Numeric id of an encyclopedia page", ()),
        ("23862", "pageid of the Python article", ()),
        ("1092923", "Wikipedia page to summarize, by numeric id", ()),
    ),
    "ticket_id": (
        (
            "9c8b7a69-5847-4362-a1b0-c9d8e7f6a5b4",
            "id of a workboard ticket to move",
            ("reminder_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "1d2e3f40-5162-4738-8a9b-c0d1e2f3a4b5",
            "Workboard ticket to comment on",
            ("reminder_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "f0e1d2c3-b4a5-4697-8879-6a5b4c3d2e1f",
            "Ticket of the board to close",
            ("reminder_id", "incident_id", "automation_id", "hue_light_id"),
        ),
        (
            "3a4b5c6d-7e8f-4901-a2b3-c4d5e6f7a8b9",
            "Which workboard card to assign",
            ("reminder_id", "incident_id", "automation_id", "hue_light_id"),
        ),
    ),
    "email_attachment_id": (
        ("ANGjdJ8wq9Xz3vB1nM5kL2pR7tY4uI0oE6aS", "Handle of an attachment of a Gmail message", ()),
        ("AAMkADNiYTE5ZmFlLTc0NjUtBGAAAAAAA=", "Outlook attachment of an email", ("message_id",)),
        ("ANGjdJ_7hG3fD9sA2qW5eR8tY1uI4oP6lK", "Attachment to read from an email", ()),
        ("2.1", "IMAP part index of an attached PDF", ()),
    ),
    "email_label_id": (
        ("Label_4728193650", "Gmail label identifier to apply", ("email_label",)),
        ("Label_12", "id of a user label in Gmail", ("email_label",)),
        ("Label_998877", "Label id to remove from a thread", ("email_label",)),
        ("Label_5", "Identifier of the 'Factures' label", ("email_label",)),
    ),
    "incident_id": (
        (
            "7b6a5948-3726-4150-9fed-cba987654321",
            "id of a platform diagnostic incident",
            ("reminder_id", "ticket_id", "automation_id", "hue_light_id"),
        ),
        (
            "2c3d4e5f-6a7b-4c8d-9e0f-1a2b3c4d5e6f",
            "Incident to fetch the diagnosis for",
            ("reminder_id", "ticket_id", "automation_id", "hue_light_id"),
        ),
        (
            "8e7d6c5b-4a39-4281-b7a6-958473625140",
            "Which platform incident to inspect",
            ("reminder_id", "ticket_id", "automation_id", "hue_light_id"),
        ),
        (
            "4f5e6d7c-8b9a-4012-b3c4-d5e6f7a8b9c0",
            "Incident identifier in the ops console",
            ("reminder_id", "ticket_id", "automation_id", "hue_light_id"),
        ),
    ),
    "devops_session_id": (
        ("sess_01J9Z8Y7X6W5V4U3T2S1R0QPON", "Remote CLI session to resume", ()),
        ("cli-session-7f3e9a2b", "Handle of a running DevOps CLI session", ()),
        ("sess_01JA1B2C3D4E5F6G7H8J9K0LMN", "CLI session to stop", ()),
        ("devops-8842-run", "Remote shell session identifier", ()),
    ),
    "hue_light_id": (
        (
            "3d8b2f9a-1c7e-4e5b-a0d6-9f2c8b7e6a51",
            "Philips Hue light resource to turn on",
            ("reminder_id", "ticket_id", "incident_id", "automation_id"),
        ),
        (
            "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "Hue bulb to dim",
            ("reminder_id", "ticket_id", "incident_id", "automation_id"),
        ),
        (
            "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
            "Light of the living room on the Hue bridge",
            ("reminder_id", "ticket_id", "incident_id", "automation_id"),
        ),
        (
            "f1e2d3c4-b5a6-4978-8695-a4b3c2d1e0f9",
            "Hue light to change colour",
            ("reminder_id", "ticket_id", "incident_id", "automation_id"),
        ),
    ),
    "automation_id": (
        (
            "0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
            "Scheduled action to pause",
            ("reminder_id", "ticket_id", "incident_id", "hue_light_id"),
        ),
        (
            "e9f8a7b6-c5d4-4e3f-a2b1-c0d9e8f7a6b5",
            "Automation to re-enable",
            ("reminder_id", "ticket_id", "incident_id", "hue_light_id"),
        ),
        (
            "5a6b7c8d-9e0f-4a1b-b2c3-d4e5f6a7b8c9",
            "Routine identifier to toggle",
            ("reminder_id", "ticket_id", "incident_id", "hue_light_id"),
        ),
        (
            "b8a9c0d1-e2f3-4041-b526-a7b8c9d0e1f2",
            "Which recurring automation to delete",
            ("reminder_id", "ticket_id", "incident_id", "hue_light_id"),
        ),
    ),
    # --------------------------------------------------------------- CATEGORY
    "file_mime_type": (
        ("application/pdf", "Type of a Drive file to filter on", ()),
        ("application/vnd.google-apps.spreadsheet", "MIME type of a Google Sheet", ()),
        ("image/png", "Type of an uploaded screenshot", ()),
        ("text/csv", "MIME type of an exported table", ()),
    ),
    "email_label": (
        ("Factures", "Gmail label shown on an email", ("email_label_id",)),
        ("Voyages/2026", "Nested label to file a message under", ()),
        ("STARRED", "System label of a Gmail message", ("email_label_id",)),
        ("Clients", "Label name to apply to a thread", ()),
    ),
    "place_type": (
        ("pharmacy", "Kind of place to search for nearby", ()),
        ("bakery", "Category of shop to find", ()),
        ("museum", "Type of place to include in the search", ()),
        ("gas_station", "Category of places along the route", ()),
    ),
    "ticket_priority": (
        ("urgent", "Priority of a workboard ticket", ()),
        ("low", "Priority to set on a new board card", ()),
        ("high", "Workboard ticket importance", ()),
        ("medium", "Priority column filter of the board", ()),
    ),
    "memory_category": (
        ("preference", "Category of a long-term memory about the user", ()),
        ("relationship", "Kind of memory stored about a person close to the user", ()),
        ("procedural", "Memory category of a how-to the user taught", ()),
        ("sensitivity", "Category of a memory about a topic to handle carefully", ()),
    ),
    "health_metric_kind": (
        ("heart_rate", "Kind of health signal to summarize", ()),
        ("steps", "Health metric to compare with the baseline", ()),
        ("steps", "Which activity measure to break down by day", ()),
        ("heart_rate", "Health signal of a watch export", ()),
    ),
    "journal_entry_kind": (
        ("directive", "Kind of an assistant journal entry", ()),
        ("portrait_facet", "Journal entry kind describing the user", ()),
        ("pattern", "Kind of journal note about a recurring behaviour", ()),
        ("directive", "Type of entry in LIA's journal", ()),
    ),
    "travel_mode": (
        ("TRANSIT", "Mode of transport of a route", ()),
        ("BICYCLE", "How the user wants to travel", ()),
        ("WALK", "Mode of a route to the station", ()),
        ("TWO_WHEELER", "Transport mode for a scooter route", ()),
    ),
    "language_code": (
        ("fr", "Language of a Wikipedia search", ("country_code",)),
        ("ja", "ISO 639-1 language of a page", ()),
        ("pt", "Language to read an article in", ()),
        ("zh", "Language code of a document", ()),
    ),
    "unit_system": (
        ("metric", "Unit system of a weather request", ()),
        ("imperial", "Units the user prefers for temperatures", ()),
        ("IMPERIAL", "Unit system of a route's distances", ()),
        ("METRIC", "Units for the routing request", ()),
    ),
    "route_mode_modifier": (
        ("AVOID_TOLLS", "Route modifier of a driving request", ()),
        ("AVOID_HIGHWAYS", "Constraint on how to compute the route", ()),
        ("AVOID_FERRIES", "Route calculation modifier for an island trip", ()),
        ("AVOID_TOLLS", "Option to compute a cheaper route", ()),
    ),
    "search_mode": (
        ("full_text", "How to search Drive files (names or content)", ()),
        ("name_only", "Drive search mode restricted to file names", ()),
        ("full_text", "Search mode to look inside documents", ()),
        ("name_only", "Mode of a file search by title", ()),
    ),
    "content_type_filter": (
        ("folders_only", "Which kind of Drive items to list", ()),
        ("files_only", "Filter to list only files", ()),
        ("all", "Content type filter of a Drive listing (files and folders)", ()),
        ("folders_only", "Restrict a Drive search to folders", ()),
    ),
    "reply_all_flag": (
        (
            "true",
            "Whether the reply goes to every recipient",
            ("only_completed_filter", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Reply-all option of an email answer",
            ("only_completed_filter", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "true",
            "Answer everyone in the thread",
            ("only_completed_filter", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Reply only to the sender",
            ("only_completed_filter", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
    ),
    "only_completed_filter": (
        (
            "true",
            "List only the tasks already done",
            ("reply_all_flag", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Do not restrict the task list to completed items",
            ("reply_all_flag", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "true",
            "Show exclusively finished to-dos",
            ("reply_all_flag", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Completed-only filter of a task search",
            ("reply_all_flag", "show_completed_filter", "open_now_filter", "shared_status"),
        ),
    ),
    "show_completed_filter": (
        (
            "true",
            "Include completed tasks in the list",
            ("reply_all_flag", "only_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Hide the tasks already done",
            ("reply_all_flag", "only_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "true",
            "Also display finished to-dos",
            ("reply_all_flag", "only_completed_filter", "open_now_filter", "shared_status"),
        ),
        (
            "false",
            "Whether done tasks appear in the listing",
            ("reply_all_flag", "only_completed_filter", "open_now_filter", "shared_status"),
        ),
    ),
    # ---------------------------------------------------------------- CONTENT
    "file_name": (
        ("Budget_2027_v3.xlsx", "Display name of a Drive file", ()),
        ("photo_vacances.jpg", "Name of an uploaded picture", ()),
        ("Contrat de bail.pdf", "Title of a document with its extension", ()),
        ("notes-reunion.md", "Name of a file shared in a chat", ()),
    ),
    "price_level": (
        ("Bon marché", "Price label of a restaurant in search results", ()),
        ("Very Expensive", "Localized price indication of a hotel", ()),
        ("Modéré", "Price level shown on a bar card", ()),
        ("Inexpensive", "Price label of a cafe", ()),
    ),
    "markdown_text": (
        (
            "## Ordre du jour\n- Budget\n- Recrutement",
            "Body of a note written in Markdown",
            ("file_content",),
        ),
        (
            "**Important** : rappeler le client _avant_ midi",
            "Formatted text of a message using Markdown",
            (),
        ),
        (
            "| Jour | Temp |\n|---|---|\n| Lun | 18 |",
            "Markdown table in a generated report",
            ("file_content",),
        ),
        ("1. Préchauffer\n2. Mélanger\n3. Cuire", "Recipe steps written in Markdown", ()),
    ),
    "html_content": (
        (
            "<p>Bonjour,<br>Voici le <b>rapport</b>.</p>",
            "HTML body of a newsletter",
            ("email_body",),
        ),
        (
            "<table><tr><td>Total</td><td>42</td></tr></table>",
            "Raw HTML of a web page fragment",
            (),
        ),
        ('<div class="card"><h2>Offre</h2></div>', "Markup returned by a web fetch", ()),
        ("<ul><li>Lait</li><li>Pain</li></ul>", "HTML list in an email", ("email_body",)),
    ),
    "email_body": (
        (
            "Bonjour Marc,\nPeux-tu me renvoyer le devis signé ?\nMerci,\nLéa",
            "Text of an email the user received",
            ("message_snippet",),
        ),
        ("Hi team, the release is postponed to Friday. Thanks!", "Body of an email to send", ()),
        (
            "Hola Ana, te confirmo la reserva para el sábado. Saludos",
            "Content of a message in the mailbox",
            ("message_snippet",),
        ),
        (
            "Guten Tag, anbei die Rechnung für Oktober. Mit freundlichen Grüßen",
            "Plain-text body of a received mail",
            (),
        ),
    ),
    "message_snippet": (
        (
            "Peux-tu me renvoyer le devis signé ? Merci…",
            "Short preview of an email in the inbox list",
            ("email_body",),
        ),
        (
            "Your order has shipped and will arrive…",
            "Snippet of a message in search results",
            ("email_body",),
        ),
        (
            "Rappel : la réunion de demain est déplacée à…",
            "Preview line of an unread email",
            ("email_body",),
        ),
        ("Votre facture du mois est disponible…", "Gmail snippet of a message", ("email_body",)),
    ),
    "file_content": (
        (
            "Chapitre 1\nIl était une fois un village au bord de la mer…",
            "Text extracted from a Drive document",
            ("markdown_text",),
        ),
        ("date,montant\n2026-10-01,42.50\n2026-10-02,13.00", "Content of a CSV file", ()),
        (
            "Procès-verbal de l'assemblée générale du 3 octobre…",
            "Text of a PDF read from Drive",
            (),
        ),
        ("import os\nprint(os.getcwd())", "Contents of a script file", ()),
    ),
    "biography": (
        (
            "Née à Lyon en 1985, ingénieure en robotique, passionnée d'escalade.",
            "Description of a person from a profile",
            ("review",),
        ),
        (
            "Marie Curie was a Polish-born physicist and chemist who conducted pioneering research on radioactivity.",
            "Summary of a person's life",
            (),
        ),
        (
            "Chef pâtissier depuis 2010, il a ouvert deux boutiques à Paris.",
            "About section of a contact",
            (),
        ),
        (
            "Leonardo da Vinci was an Italian polymath of the High Renaissance.",
            "Short life story of a historical figure",
            (),
        ),
    ),
    "review": (
        (
            "Super accueil, les croissants sont excellents. Je recommande !",
            "Comment left by a customer on a bakery",
            ("biography",),
        ),
        ("Room was small but very clean, staff friendly. 4/5", "Guest feedback on a hotel", ()),
        ("Service lent, plats tièdes. Décevant.", "Opinion of a diner about a restaurant", ()),
        ("Great coffee, terrible wifi.", "User review of a cafe", ()),
    ),
    "citation_url": (
        (
            "https://www.lemonde.fr/economie/article/2026/10/09/inflation.html",
            "Source link cited in a web search answer",
            ("website_url",),
        ),
        (
            "https://en.wikipedia.org/wiki/Bayeux_Tapestry",
            "Reference URL of an answer",
            ("website_url",),
        ),
        (
            "https://www.nature.com/articles/s41586-026-01234-5",
            "Citation backing a claim in a research summary",
            ("website_url",),
        ),
        (
            "https://www.insee.fr/fr/statistiques/1234567",
            "Source of a statistic in an answer",
            ("website_url",),
        ),
    ),
    "message_headers": (
        (
            "From: Léa Fontaine <lea@example.test>\nTo: Marc <marc@example.test>\nSubject: Devis",
            "Header block of an email",
            ("email_body",),
        ),
        (
            "Subject: Facture octobre\nDate: Fri, 9 Oct 2026 10:12:00 +0200",
            "Headers of a received message",
            (),
        ),
        (
            "Reply-To: noreply@shop.example\nMessage-ID: <abc123@shop.example>",
            "Technical headers of a newsletter",
            (),
        ),
        (
            "Cc: equipe@example.test\nFrom: rh@example.test",
            "Header fields of an internal email",
            (),
        ),
    ),
    "attachment_info": (
        (
            "devis_signé.pdf (application/pdf, 184 KB)",
            "Metadata of a file attached to an email",
            ("file_name",),
        ),
        (
            "2 attachments: photo1.jpg (2.1 MB), photo2.jpg (1.8 MB)",
            "Attachment summary of a message",
            (),
        ),
        (
            "Rechnung_Oktober.pdf — 96 KB — application/pdf",
            "Description of an attached invoice",
            ("file_name",),
        ),
        ("slides.pptx (pptx, 4.5 MB)", "Info about the file joined to a mail", ("file_name",)),
    ),
    "conference_link": (
        (
            "https://meet.google.com/abc-defg-hij",
            "Video call link of a calendar event",
            ("website_url",),
        ),
        (
            "https://us02web.zoom.us/j/81234567890",
            "Zoom link of a meeting invitation",
            ("website_url",),
        ),
        (
            "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc",
            "Link to join an online meeting",
            ("website_url",),
        ),
        (
            "https://meet.jit.si/ProjetAtlasHebdo",
            "Video conference URL of a weekly call",
            ("website_url",),
        ),
    ),
    "URL": (
        (
            "https://files.example.org/exports/rapport-2026-10.pdf",
            "A link pasted in a chat message",
            ("website_url",),
        ),
        ("https://cdn.example.net/img/plan-acces.png", "Link to an image found in a document", ()),
        (
            "https://example.com/s/9f8e7d?ref=mail",
            "Tracking link at the bottom of an email",
            ("website_url",),
        ),
        ("ftp://ftp.example.org/pub/dataset.csv", "Location of a downloadable dataset", ()),
    ),
    "website_url": (
        ("https://www.boulangerie-dupain.fr", "Website of a bakery in place details", ()),
        ("https://acme-industries.example", "Homepage of a company", ()),
        ("https://www.museo-prado.es", "Official site of a museum", ()),
        ("https://www.hotel-des-arts.example/fr", "Site of a hotel found in search results", ()),
    ),
    "google_maps_url": (
        (
            "https://maps.google.com/?cid=1234567890123456789",
            "Map link of a place",
            ("website_url",),
        ),
        (
            "https://www.google.com/maps/dir/?api=1&destination=Lyon",
            "Link opening directions to a destination",
            ("website_url",),
        ),
        ("https://goo.gl/maps/AbCdEfGh123", "Short map link shared by a friend", ("website_url",)),
        (
            "https://www.google.com/maps/place/?q=place_id:ChIJLU7jZClu5kcR4PcOOO6p3I0",
            "Link to show a monument on the map",
            ("website_url",),
        ),
    ),
    "navigation_steps": (
        (
            '[{"instruction": "Tournez à droite sur la rue de Rivoli", "distance": "200 m"}, {"instruction": "Continuez tout droit", "distance": "1,2 km"}]',
            "Turn-by-turn instructions of a route",
            (),
        ),
        (
            "1. Head north on Main St (300 m)\n2. Turn left onto Oak Ave (1.1 km)",
            "Directions of a walking route",
            (),
        ),
        (
            '[{"instruction": "Prenez la sortie 3"}, {"instruction": "Serrez à gauche"}]',
            "Steps returned by the routing service",
            (),
        ),
        (
            "1. Rechts abbiegen auf die Hauptstraße\n2. Nach 500 m links",
            "Driving directions step by step",
            (),
        ),
    ),
    "route_matrix": (
        (
            '[[{"distance_km": 12.3, "duration_minutes": 21}, {"distance_km": 4.1, "duration_minutes": 9}]]',
            "Distances from one origin to two destinations",
            (),
        ),
        (
            '[[{"distance_km": 3.0, "duration_minutes": 8, "condition": "ROUTE_EXISTS"}], [{"distance_km": 7.4, "duration_minutes": 15, "condition": "ROUTE_EXISTS"}]]',
            "Travel times between several origins and a destination",
            (),
        ),
        (
            '[[{"distance_km": 1.1, "duration_minutes": 14}, {"distance_km": 2.2, "duration_minutes": 27}, {"distance_km": 0.6, "duration_minutes": 8}]]',
            "Walking times from the hotel to three museums",
            (),
        ),
        (
            '[[{"distance_km": 55.0, "duration_minutes": 41}], [{"distance_km": 61.2, "duration_minutes": 47}]]',
            "Matrix of drive times between two depots and a client",
            (),
        ),
    ),
    "optimal_order": (
        ("[2, 0, 1]", "Best order to visit the destinations of a route matrix", ()),
        ("[1, 3, 0, 2]", "Optimal sequence of deliveries", ()),
        ("[0, 2, 1]", "Order in which to visit three shops", ()),
        ("[3, 1, 2, 0]", "Optimized visiting order of four clients", ()),
    ),
    # ----------------------------------------------------------------- STATUS
    "ticket_status": (
        ("in_progress", "Column of a workboard ticket", ()),
        ("waiting", "State of a board card blocked on someone", ()),
        ("done", "Workboard column of a finished ticket", ("task_status",)),
        ("confirming", "Ticket column awaiting the owner's confirmation", ()),
    ),
    "identity_confidence": (
        ("exact", "How a relationship's identity was matched", ()),
        ("normalized", "Identity matching verdict of a CRM entry", ()),
        ("normalized", "Whether names matched after folding accents", ()),
        ("exact", "Verdict of matching a sender to a contact", ()),
    ),
    "effect_status": (
        ("succeeded", "Outcome of an action LIA performed", ()),
        ("refused", "Recorded outcome of a blocked action", ()),
        ("abandoned", "Outcome of an action interrupted mid-way", ()),
        ("claimed", "State of an action recorded before it ran", ()),
    ),
    "traffic_condition": (
        ("HEAVY", "Traffic on the route right now", ()),
        ("LIGHT", "Current traffic level of a drive", ()),
        ("MODERATE", "Congestion level on the motorway", ()),
        ("NORMAL", "Traffic condition returned with a route", ()),
    ),
    "task_status": (
        ("needsAction", "Status of a to-do item", ()),
        ("completed", "Status of a task already done", ("ticket_status",)),
        ("needsAction", "Whether a Google task is still open", ()),
        ("completed", "Completion state of a to-do", ()),
    ),
    "access_role": (
        ("writer", "User's permission on a shared calendar", ()),
        ("reader", "Access level to a colleague's agenda", ()),
        ("owner", "Role of the user on their own calendar", ()),
        ("reader", "Permission on a public holidays calendar", ()),
    ),
    "shared_status": (
        (
            "true",
            "Whether a Drive file is shared",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "open_now_filter"),
        ),
        (
            "false",
            "Sharing state of a private document",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "open_now_filter"),
        ),
        (
            "true",
            "Is this spreadsheet shared with others",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "open_now_filter"),
        ),
        (
            "false",
            "Whether a folder is visible to other people",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "open_now_filter"),
        ),
    ),
    "location_source": (
        ("gps", "Where the user's position came from", ()),
        ("address_lookup", "Source of a location (geocoded from an address)", ()),
        ("user_input", "Origin of a location typed by the user", ()),
        ("gps", "How the current position was obtained", ()),
    ),
    "business_status": (
        ("CLOSED_TEMPORARILY", "Operating state of a restaurant in place details", ()),
        ("CLOSED_PERMANENTLY", "Status of a shop that shut down", ()),
        ("OPERATIONAL", "Business state of a pharmacy", ("operation_status",)),
        ("CLOSED_TEMPORARILY", "Whether the museum is open as a business", ()),
    ),
    "operation_status": (
        ("open", "Current operational state of a service", ("business_status",)),
        ("closed", "Whether a facility is operating right now", ("business_status",)),
        ("closed", "Operational state of a ski lift", ("business_status",)),
        ("open", "Status of a ferry line today", ("business_status",)),
    ),
    "send_updates_option": (
        ("externalOnly", "Who receives notifications when the event changes", ()),
        ("all", "Whether to notify attendees of a calendar change", ()),
        ("none", "Send no update emails for the event edit", ()),
        ("all", "Notification option when cancelling a meeting", ()),
    ),
    "open_now_filter": (
        (
            "true",
            "Only places open at the moment",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "shared_status"),
        ),
        (
            "false",
            "Do not filter places on current opening",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "shared_status"),
        ),
        (
            "true",
            "Restrict the search to pharmacies open now",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "shared_status"),
        ),
        (
            "false",
            "Opening filter of a restaurant search",
            ("reply_all_flag", "only_completed_filter", "show_completed_filter", "shared_status"),
        ),
    ),
    "route_condition": (
        ("ROUTE_NOT_FOUND", "Condition of one origin-destination element of a route matrix", ()),
        ("ROUTE_EXISTS", "Whether a route could be computed between two points", ()),
        ("ROUTE_NOT_FOUND", "Element condition for an unreachable island", ()),
        ("OK", "Condition of a matrix element", ()),
    ),
    "degree_of_openness": (
        ("partially_open", "How accessible a mountain pass is", ("operation_status",)),
        ("fully_open", "Openness of a hiking trail", ("operation_status",)),
        ("closed_to_traffic", "Degree to which a road is open", ("operation_status",)),
        ("partially_open", "Accessibility of a park during works", ("operation_status",)),
    ),
}


#: Types no tool emits or reads (census 2026-10-11): reported apart, since their
#: values are the registry's own illustrations rather than a vocabulary of the code.
UNWIRED_TYPES = frozenset(
    {
        "location_source",
        "operation_status",
        "degree_of_openness",
        "route_mode_modifier",
        "waypoint",
        "coordinate",
        "duration",
    }
)

#: The values the CODE actually emits or accepts, per typed vocabulary (census
#: 2026-10-11, with sources in docs/technical/JEV_SEMANTIC_QUALIFICATION.md). The
#: "aligned" criteria variant appends them to the registry description — what the
#: registry would publish once aligned with the code.
CODE_VOCABULARY: dict[str, str] = {
    "ticket_status": "idea, todo, in_progress, waiting, confirming, validating, done",
    "ticket_priority": "low, medium, high, urgent",
    "memory_category": "preference, personal, relationship, event, pattern, sensitivity, procedural",
    "health_metric_kind": "heart_rate, steps",
    "journal_entry_kind": "directive, pattern, portrait_facet",
    "identity_confidence": "exact, normalized",
    "effect_status": "claimed, succeeded, failed, abandoned, refused, waiting",
    "task_status": "needsAction, completed",
    "access_role": "owner, writer, reader",
    "shared_status": "true, false",
    "business_status": "OPERATIONAL, CLOSED_TEMPORARILY, CLOSED_PERMANENTLY",
    "send_updates_option": "all, externalOnly, none",
    "open_now_filter": "true, false",
    "traffic_condition": "NORMAL, LIGHT, MODERATE, HEAVY",
    "route_condition": "OK, ROUTE_EXISTS, ROUTE_NOT_FOUND",
    "travel_mode": "DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER",
    "unit_system": "metric, imperial (weather); METRIC, IMPERIAL (routes)",
    "search_mode": "name_only, full_text",
    "content_type_filter": "files_only, folders_only, all",
    "reply_all_flag": "true, false",
    "only_completed_filter": "true, false",
    "show_completed_filter": "true, false",
    "recency_filter": "day, week, month, year; pd, pw, pm, py; 1d, 7d, 30d, 1y",
    "price_level": "a localized label (e.g. Inexpensive, Bon marché, Very Expensive)",
    "email_label": "a user label name or path, or a system label (INBOX, STARRED, ...)",
    "email_label_id": "Label_<digits>, or a system id such as INBOX",
    "contact_id": "people/c<digits>",
    "place_id": "ChIJ... (Google Place id)",
    "reminder_id": "UUID",
    "ticket_id": "UUID",
    "incident_id": "UUID",
    "automation_id": "UUID",
    "hue_light_id": "UUID (Hue CLIP v2 resource id)",
    "wikipedia_page_id": "integer",
    "unix_timestamp": "integer seconds since 1970-01-01",
    "duration_minutes": "integer minutes",
}


def build(split: Split, parents: dict[str, str | None]) -> tuple[Case, ...]:
    """The split's cases; ``parents`` (type -> parent) gives the lenient ancestors."""

    def ancestors(name: str) -> tuple[str, ...]:
        chain: list[str] = []
        parent = parents.get(name)
        while parent:
            chain.append(parent)
            parent = parents.get(parent)
        return tuple(chain)

    offset = 0 if split == "calibration" else 2
    cases: list[Case] = []
    index = 0
    for type_name, quartet in CASES.items():
        for value, context, also in quartet[offset : offset + 2]:
            index += 1
            cases.append(
                single(
                    "d2",
                    split,
                    index,
                    "en",
                    "unwired:" + type_name if type_name in UNWIRED_TYPES else type_name,
                    {"value": value, "context": context},
                    type_name,
                    also,
                    lenient=ancestors(type_name),
                )
            )
    return tuple(cases)
