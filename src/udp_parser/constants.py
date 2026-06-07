# Weather types
WEATHER_TYPES = {
    0: "Clear",
    1: "Light Cloud",
    2: "Overcast",
    3: "Light Rain",
    4: "Heavy Rain",
    5: "Storm",
}

# Session types
SESSION_TYPES = {
    0: "Unknown",
    1: "Practice 1",
    2: "Practice 2",
    3: "Practice 3",
    4: "Short Practice",
    5: "Qualifying 1",
    6: "Qualifying 2",
    7: "Qualifying 3",
    8: "Short Qualifying",
    9: "One-Shot Qualifying",
    10: "Sprint Shootout 1",
    11: "Sprint Shootout 2",
    12: "Sprint Shootout 3",
    13: "Short Sprint Shootout",
    14: "One-Shot Sprint Shootout",
    15: "Race",
    16: "Race 2",
    17: "Feature Race",
    18: "Time Trial",
}

# Surface types
SURFACE_TYPES = {
    0: "Tarmac",
    1: "Rumble Strip",
    2: "Concrete",
    3: "Rock",
    4: "Gravel",
    5: "Mud",
    6: "Sand",
    7: "Grass",
    8: "Water",
    9: "Cobblestone",
    10: "Metal",
    11: "Ridged",
}

# Button flags
BUTTON_FLAGS = {
    0x00000001: "Cross/A",
    0x00000002: "Triangle/Y",
    0x00000004: "Circle/B",
    0x00000008: "Square/X",
    0x00000010: "D-pad Left",
    0x00000020: "D-pad Right",
    0x00000040: "D-pad Up",
    0x00000080: "D-pad Down",
    0x00000100: "Options/Menu",
    0x00000200: "L1/LB",
    0x00000400: "R1/RB",
    0x00000800: "L2/LT",
    0x00001000: "R2/RT",
    0x00002000: "Left Stick Click",
    0x00004000: "Right Stick Click",
    0x00008000: "Right Stick Left",
    0x00010000: "Right Stick Right",
    0x00020000: "Right Stick Up",
    0x00040000: "Right Stick Down",
    0x00080000: "Special",
    0x00100000: "UDP Action 1",
    0x00200000: "UDP Action 2",
    0x00400000: "UDP Action 3",
    0x00800000: "UDP Action 4",
    0x01000000: "UDP Action 5",
    0x02000000: "UDP Action 6",
    0x04000000: "UDP Action 7",
    0x08000000: "UDP Action 8",
    0x10000000: "UDP Action 9",
    0x20000000: "UDP Action 10",
    0x40000000: "UDP Action 11",
    0x80000000: "UDP Action 12",
}

# Tyre compounds (F1 Modern)
TYRE_COMPOUNDS = {
    16: "C5",
    17: "C4",
    18: "C3",
    19: "C2",
    20: "C1",
    21: "C0",
    22: "C6",
    7: "Inter",
    8: "Wet",
}

# Visual tyre compounds shown in-game
VISUAL_TYRE_COMPOUNDS = {16: "Soft", 17: "Medium", 18: "Hard", 7: "Inter", 8: "Wet"}

# ERS deployment modes
ERS_DEPLOYMENT_MODES = {0: "None", 1: "Medium", 2: "Hotlap", 3: "Overtake"}

# Flag colors
FLAG_COLORS = {-1: "Invalid/Unknown", 0: "None", 1: "Green", 2: "Blue", 3: "Yellow", 4: "Red"}

# Result status
RESULT_STATUS = {
    0: "Invalid",
    1: "Inactive",
    2: "Active",
    3: "Finished",
    4: "DNF",
    5: "DSQ",
    6: "Not Classified",
    7: "Retired",
}

# Driver status
DRIVER_STATUS = {0: "In Garage", 1: "Flying Lap", 2: "In Lap", 3: "Out Lap", 4: "On Track"}

# Max ERS energy in Joules
MAX_ERS_ENERGY = 4000000

# Team IDs (Complete list from F1 25 docs)
TEAM_NAMES = {
    0: "Mercedes",
    1: "Ferrari",
    2: "Red Bull Racing",
    3: "Williams",
    4: "Aston Martin",
    5: "Alpine",
    6: "RB",
    7: "Haas",
    8: "McLaren",
    9: "Sauber",
    41: "F1 Generic",
    104: "F1 Custom Team",
    129: "Konnersport",
    142: "APXGP '24",
    154: "APXGP '25",
    155: "Konnersport '24",
    158: "Art GP '24",
    159: "Campos '24",
    160: "Rodin Motorsport '24",
    161: "AIX Racing '24",
    162: "DAMS '24",
    163: "Hitech '24",
    164: "MP Motorsport '24",
    165: "Prema '24",
    166: "Trident '24",
    167: "Van Amersfoort Racing '24",
    168: "Invicta '24",
    185: "Mercedes '24",
    186: "Ferrari '24",
    187: "Red Bull Racing '24",
    188: "Williams '24",
    189: "Aston Martin '24",
    190: "Alpine '24",
    191: "RB '24",
    192: "Haas '24",
    193: "McLaren '24",
    194: "Sauber '24",
}

# Track IDs
TRACK_NAMES = {
    0: "Melbourne",
    1: "Paul Ricard",
    2: "Shanghai",
    3: "Sakhir (Bahrain)",
    4: "Catalunya",
    5: "Monaco",
    6: "Montreal",
    7: "Silverstone",
    8: "Hockenheim",
    9: "Hungaroring",
    10: "Spa",
    11: "Monza",
    12: "Singapore",
    13: "Suzuka",
    14: "Abu Dhabi",
    15: "Texas",
    16: "Brazil",
    17: "Austria",
    18: "Sochi",
    19: "Mexico",
    20: "Baku (Azerbaijan)",
    21: "Sakhir Short",
    22: "Silverstone Short",
    23: "Texas Short",
    24: "Suzuka Short",
    25: "Hanoi",
    26: "Zandvoort",
    27: "Imola",
    28: "Portimão",
    29: "Jeddah",
    30: "Miami",
    31: "Las Vegas",
    32: "Losail",
    39: "Silverstone (Reverse)",
    40: "Austria (Reverse)",
    41: "Zandvoort (Reverse)",
}

# Nationality IDs
NATIONALITY_NAMES = {
    1: "American",
    2: "Argentinean",
    3: "Australian",
    4: "Austrian",
    5: "Azerbaijani",
    6: "Bahraini",
    7: "Belgian",
    8: "Bolivian",
    9: "Brazilian",
    10: "British",
    11: "Bulgarian",
    12: "Cameroonian",
    13: "Canadian",
    14: "Chilean",
    15: "Chinese",
    16: "Colombian",
    17: "Costa Rican",
    18: "Croatian",
    19: "Cypriot",
    20: "Czech",
    21: "Danish",
    22: "Dutch",
    23: "Ecuadorian",
    24: "English",
    25: "Emirian",
    26: "Estonian",
    27: "Finnish",
    28: "French",
    29: "German",
    30: "Ghanaian",
    31: "Greek",
    32: "Guatemalan",
    33: "Honduran",
    34: "Hong Konger",
    35: "Hungarian",
    36: "Icelander",
    37: "Indian",
    38: "Indonesian",
    39: "Irish",
    40: "Israeli",
    41: "Italian",
    42: "Jamaican",
    43: "Japanese",
    44: "Jordanian",
    45: "Kuwaiti",
    46: "Latvian",
    47: "Lebanese",
    48: "Lithuanian",
    49: "Luxembourger",
    50: "Malaysian",
    51: "Maltese",
    52: "Mexican",
    53: "Monegasque",
    54: "New Zealander",
    55: "Nicaraguan",
    56: "Northern Irish",
    57: "Norwegian",
    58: "Omani",
    59: "Pakistani",
    60: "Panamanian",
    61: "Paraguayan",
    62: "Peruvian",
    63: "Polish",
    64: "Portuguese",
    65: "Qatari",
    66: "Romanian",
    67: "Russian",
    68: "Salvadoran",
    69: "Saudi",
    70: "Scottish",
    71: "Serbian",
    72: "Singaporean",
    73: "Slovakian",
    74: "Slovenian",
    75: "South Korean",
    76: "South African",
    77: "Spanish",
    78: "Swedish",
    79: "Swiss",
    80: "Thai",
    81: "Turkish",
    82: "Uruguayan",
    83: "Ukrainian",
    84: "Venezuelan",
    85: "Barbadian",
    86: "Welsh",
    87: "Vietnamese",
    88: "Algerian",
    89: "Bosnian",
    90: "Filipino",
}

# Game Mode IDs (F1 25)
GAME_MODES = {
    4: "Grand Prix '23",
    5: "Time Trial",
    6: "Splitscreen",
    7: "Online Custom",
    15: "Online Weekly Event",
    17: "Story Mode (Braking Point)",
    27: "My Team Career '25",
    28: "Driver Career '25",
    29: "Career '25 Online",
    30: "Challenge Career '25",
    75: "Story Mode (APXGP)",
    127: "Benchmark",
}

# Ruleset IDs
RULESETS = {0: "Practice & Qualifying", 1: "Race", 2: "Time Trial", 12: "Elimination"}

# Penalty Types
PENALTY_TYPES = {
    0: "Drive through",
    1: "Stop Go",
    2: "Grid penalty",
    3: "Penalty reminder",
    4: "Time penalty",
    5: "Warning",
    6: "Disqualified",
    7: "Removed from formation lap",
    8: "Parked too long timer",
    9: "Tyre regulations",
    10: "This lap invalidated",
    11: "This and next lap invalidated",
    12: "This lap invalidated without reason",
    13: "This and next lap invalidated without reason",
    14: "This and previous lap invalidated",
    15: "This and previous lap invalidated without reason",
    16: "Retired",
    17: "Black flag timer",
}

# Infringement Types
INFRINGEMENT_TYPES = {
    0: "Blocking by slow driving",
    1: "Blocking by wrong way driving",
    2: "Reversing off the start line",
    3: "Big Collision",
    4: "Small Collision",
    5: "Collision failed to hand back position single",
    6: "Collision failed to hand back position multiple",
    7: "Corner cutting gained time",
    8: "Corner cutting overtake single",
    9: "Corner cutting overtake multiple",
    10: "Crossed pit exit lane",
    11: "Ignoring blue flags",
    12: "Ignoring yellow flags",
    13: "Ignoring drive through",
    14: "Too many drive throughs",
    15: "Drive through reminder serve within n laps",
    16: "Drive through reminder serve this lap",
    17: "Pit lane speeding",
    18: "Parked for too long",
    19: "Ignoring tyre regulations",
    20: "Too many penalties",
    21: "Multiple warnings",
    22: "Approaching disqualification",
    23: "Tyre regulations select single",
    24: "Tyre regulations select multiple",
    25: "Lap invalidated corner cutting",
    26: "Lap invalidated running wide",
    27: "Corner cutting ran wide gained time minor",
    28: "Corner cutting ran wide gained time significant",
    29: "Corner cutting ran wide gained time extreme",
    30: "Lap invalidated wall riding",
    31: "Lap invalidated flashback used",
    32: "Lap invalidated reset to track",
    33: "Blocking the pitlane",
    34: "Jump start",
    35: "Safety car to car collision",
    36: "Safety car illegal overtake",
    37: "Safety car exceeding allowed pace",
    38: "Virtual safety car exceeding allowed pace",
    39: "Formation lap below allowed speed",
    40: "Formation lap parking",
    41: "Retired mechanical failure",
    42: "Retired terminally damaged",
    43: "Safety car falling too far back",
    44: "Black flag timer",
    45: "Unserved stop go penalty",
    46: "Unserved drive through penalty",
    47: "Engine component change",
    48: "Gearbox change",
    49: "Parc Fermé change",
    50: "League grid penalty",
    51: "Retry penalty",
    52: "Illegal time gain",
    53: "Mandatory pitstop",
    54: "Attribute assigned",
}

# Event String Codes
EVENT_CODES = {
    "SSTA": "Session Started",
    "SEND": "Session Ended",
    "FTLP": "Fastest Lap",
    "RTMT": "Retirement",
    "DRSE": "DRS enabled",
    "DRSD": "DRS disabled",
    "TMPT": "Team mate in pits",
    "CHQF": "Chequered flag",
    "RCWN": "Race Winner",
    "PENA": "Penalty Issued",
    "SPTP": "Speed Trap Triggered",
    "STLG": "Start lights",
    "LGOT": "Lights out",
    "DTSV": "Drive through served",
    "SGSV": "Stop go served",
    "FLBK": "Flashback",
    "BUTN": "Button status",
    "RDFL": "Red Flag",
    "OVTK": "Overtake",
    "SCAR": "Safety Car",
    "COLL": "Collision",
}

# Pit Status
PIT_STATUS = {0: "None", 1: "Pitting", 2: "In pit area"}

# Sector numbers
SECTORS = {0: "Sector 1", 1: "Sector 2", 2: "Sector 3"}

# Safety Car Status
SAFETY_CAR_STATUS = {
    0: "No safety car",
    1: "Full safety car",
    2: "Virtual safety car",
    3: "Formation lap",
}

# Formula types
FORMULA_TYPES = {
    0: "F1 Modern",
    1: "F1 Classic",
    2: "F2",
    3: "F1 Generic",
    4: "Beta",
    5: "Supercars",
    6: "Esports",
    7: "F2 2021",
}

# Session Length
SESSION_LENGTH = {
    0: "None",
    2: "Very Short",
    3: "Short",
    4: "Medium",
    5: "Medium Long",
    6: "Long",
    7: "Full",
}

SESSION_WATCH_KEYS = [
    "weatherName",
    "trackTemperature",
    "airTemperature",
    "sessionTypeName",
    "safetyCarStatusName",
    "drsAllowed",
]

SESSION_FORECAST_KEYS = [
    "forecastSamples",
    "weatherForecast",
    "forecast",
    "forecast_data",
]

SESSION_MARSHAL_KEYS = [
    "marshalZones",
    "marshalZonesFlags",
]

SPEED_UNITS = {
    0: "MPH",
    1: "KPH",
}

TEMPERATURE_UNITS = {
    0: "Celsius",
    1: "Fahrenheit",
}

RECOVERY_MODES = {
    0: "None",
    1: "Flashbacks",
    2: "Auto-recovery",
}

FLASHBACK_LIMITS = {
    0: "Low",
    1: "Medium",
    2: "High",
    3: "Unlimited",
}

SESSION_SURFACE_MODES = {
    0: "Simplified",
    1: "Realistic",
}

LOW_FUEL_MODES = {
    0: "Easy",
    1: "Hard",
}

RACE_START_MODES = {
    0: "Manual",
    1: "Assisted",
}

TYRE_TEMPERATURE_MODES = {
    0: "Surface only",
    1: "Surface & Carcass",
}

PIT_LANE_TYRE_SIM = {
    0: "On",
    1: "Off",
}

CAR_DAMAGE_LEVELS = {
    0: "Off",
    1: "Reduced",
    2: "Standard",
    3: "Simulation",
}

CAR_DAMAGE_RATES = {
    0: "Reduced",
    1: "Standard",
    2: "Simulation",
}

COLLISION_MODES = {
    0: "Off",
    1: "Player-to-Player Off",
    2: "On",
}

COLLISION_FIRST_LAP = {
    0: "Disabled",
    1: "Enabled",
}

MULTIPLAYER_UNSAFE_PIT_RELEASE = {
    0: "On",
    1: "Off",
}

MULTIPLAYER_GRIEFING = {
    0: "Disabled",
    1: "Enabled",
}

CORNER_CUTTING_STRINGENCY = {
    0: "Regular",
    1: "Strict",
}

PARC_FERME_RULES = {
    0: "Off",
    1: "On",
}

PIT_STOP_EXPERIENCE = {
    0: "Automatic",
    1: "Broadcast",
    2: "Immersive",
}

SAFETY_CAR_LEVELS = {
    0: "Off",
    1: "Reduced",
    2: "Standard",
    3: "Increased",
}

SAFETY_CAR_EXPERIENCE = {
    0: "Broadcast",
    1: "Immersive",
}

FORMATION_LAP_MODES = {
    0: "Off",
    1: "On",
}

FORMATION_LAP_EXPERIENCE = {
    0: "Broadcast",
    1: "Immersive",
}

RED_FLAG_LEVELS = {
    0: "Off",
    1: "Reduced",
    2: "Standard",
    3: "Increased",
}

LICENCE_EFFECTS = {
    0: "Off",
    1: "On",
}

SESSION_WATCH_KEYS = [
    "weatherName",
    "trackTemperature",
    "airTemperature",
    "sessionTypeName",
    "safetyCarStatusName",
    "drsAllowed",
]

SESSION_FORECAST_KEYS = [
    "forecastSamples",
    "weatherForecast",
    "forecast",
    "forecast_data",
]

SESSION_MARSHAL_KEYS = [
    "marshalZones",
    "marshalZonesFlags",
]

# Fuel Mix
FUEL_MIX = {0: "Lean", 1: "Standard", 2: "Rich", 3: "Max"}

# Traction Control
TRACTION_CONTROL = {0: "Off", 1: "Medium", 2: "Full"}

# Anti-lock Brakes
ANTI_LOCK_BRAKES = {0: "Off", 1: "On"}

# DRS Status
DRS_STATUS = {0: "Off", 1: "On"}

# Ready Status (Lobby)
READY_STATUS = {0: "Not ready", 1: "Ready", 2: "Spectating"}

# Assist levels
ASSIST_LEVELS = {0: "Off", 1: "Low", 2: "Medium", 3: "High"}

# Gearbox Assist
GEARBOX_ASSIST = {1: "Manual", 2: "Manual & suggested gear", 3: "Auto"}

# Dynamic Racing Line
DYNAMIC_RACING_LINE = {0: "Off", 1: "Corners only", 2: "Full"}

# Dynamic Racing Line Type
DYNAMIC_RACING_LINE_TYPE = {0: "2D", 1: "3D"}

# Driver IDs (Complete list from F1 25 docs)
DRIVER_NAMES = {
    0: "Carlos Sainz",
    1: "Daniil Kvyat",
    2: "Daniel Ricciardo",
    3: "Fernando Alonso",
    4: "Felipe Massa",
    6: "Kimi Räikkönen",
    7: "Lewis Hamilton",
    9: "Max Verstappen",
    10: "Nico Hulkenburg",
    11: "Kevin Magnussen",
    12: "Romain Grosjean",
    13: "Sebastian Vettel",
    14: "Sergio Perez",
    15: "Valtteri Bottas",
    17: "Esteban Ocon",
    19: "Lance Stroll",
    20: "Arron Barnes",
    21: "Martin Giles",
    22: "Alex Murray",
    23: "Lucas Roth",
    24: "Igor Correia",
    25: "Sophie Levasseur",
    26: "Jonas Schiffer",
    27: "Alain Forest",
    28: "Jay Letourneau",
    29: "Esto Saari",
    30: "Yasar Atiyeh",
    31: "Callisto Calabresi",
    32: "Naota Izum",
    33: "Howard Clarke",
    34: "Wilheim Kaufmann",
    35: "Marie Laursen",
    36: "Flavio Nieves",
    37: "Peter Belousov",
    38: "Klimek Michalski",
    39: "Santiago Moreno",
    40: "Benjamin Coppens",
    41: "Noah Visser",
    42: "Gert Waldmuller",
    43: "Julian Quesada",
    44: "Daniel Jones",
    45: "Artem Markelov",
    46: "Tadasuke Makino",
    47: "Sean Gelael",
    48: "Nyck De Vries",
    49: "Jack Aitken",
    50: "George Russell",
    51: "Maximilian Günther",
    52: "Nirei Fukuzumi",
    53: "Luca Ghiotto",
    54: "Lando Norris",
    55: "Sérgio Sette Câmara",
    56: "Louis Delétraz",
    57: "Antonio Fuoco",
    58: "Charles Leclerc",
    59: "Pierre Gasly",
    62: "Alexander Albon",
    63: "Nicholas Latifi",
    64: "Dorian Boccolacci",
    65: "Niko Kari",
    66: "Roberto Merhi",
    67: "Arjun Maini",
    68: "Alessio Lorandi",
    69: "Ruben Meijer",
    70: "Rashid Nair",
    71: "Jack Tremblay",
    72: "Devon Butler",
    73: "Lukas Weber",
    74: "Antonio Giovinazzi",
    75: "Robert Kubica",
    76: "Alain Prost",
    77: "Ayrton Senna",
    78: "Nobuharu Matsushita",
    79: "Nikita Mazepin",
    80: "Guanya Zhou",
    81: "Mick Schumacher",
    82: "Callum Ilott",
    83: "Juan Manuel Correa",
    84: "Jordan King",
    85: "Mahaveer Raghunathan",
    86: "Tatiana Calderon",
    87: "Anthoine Hubert",
    88: "Guiliano Alesi",
    89: "Ralph Boschung",
    90: "Michael Schumacher",
    91: "Dan Ticktum",
    92: "Marcus Armstrong",
    93: "Christian Lundgaard",
    94: "Yuki Tsunoda",
    95: "Jehan Daruvala",
    96: "Gulherme Samaia",
    97: "Pedro Piquet",
    98: "Felipe Drugovich",
    99: "Robert Schwartzman",
    100: "Roy Nissany",
    101: "Marino Sato",
    102: "Aidan Jackson",
    103: "Casper Akkerman",
    109: "Jenson Button",
    110: "David Coulthard",
    111: "Nico Rosberg",
    112: "Oscar Piastri",
    113: "Liam Lawson",
    114: "Juri Vips",
    115: "Theo Pourchaire",
    116: "Richard Verschoor",
    117: "Lirim Zendeli",
    118: "David Beckmann",
    121: "Alessio Deledda",
    122: "Bent Viscaal",
    123: "Enzo Fittipaldi",
    125: "Mark Webber",
    126: "Jacques Villeneuve",
    127: "Jake Hughes",
    128: "Frederik Vesti",
    129: "Olli Caldwell",
    130: "Logan Sargeant",
    131: "Cem Bolukbasi",
    132: "Ayuma Iwasa",
    133: "Clement Novolak",
    134: "Dennis Hauger",
    135: "Calan Williams",
    136: "Jack Doohan",
    137: "Amaury Cordeel",
    138: "Mika Hakkinen",
    145: "Zane Maloney",
    146: "Victor Martins",
    147: "Oliver Bearman",
    148: "Jak Crawford",
    149: "Isack Hadjar",
    152: "Roman Stanek",
    153: "Kush Maini",
    156: "Brendon Leigh",
    157: "David Tonizza",
    158: "Jarno Opmeer",
    159: "Lucas Blakeley",
    160: "Paul Aron",
    161: "Gabriel Bortoleto",
    162: "Franco Colapinto",
    163: "Taylor Barnard",
    164: "Joshua Dürksen",
    165: "Andrea-Kimi Antonelli",
    166: "Ritomo Miyata",
    167: "Rafael Villagómez",
    168: "Zak O'Sullivan",
    169: "Pepe Marti",
    170: "Sonny Hayes",
    171: "Joshua Pearce",
    172: "Callum Voisin",
    173: "Matias Zagazeta",
    174: "Nikola Tsolov",
    175: "Tim Tramnitz",
    185: "Luca Cortez",
}

# Packet IDs
PACKET_IDS = {
    0: "Motion",
    1: "Session",
    2: "Lap Data",
    3: "Event",
    4: "Participants",
    5: "Car Setups",
    6: "Car Telemetry",
    7: "Car Status",
    8: "Final Classification",
    9: "Lobby Info",
    10: "Car Damage",
    11: "Session History",
    12: "Tyre Sets",
    13: "Motion Ex",
    14: "Time Trial",
    15: "Lap Positions",
}

# MFD Panel Index
MFD_PANELS = {
    0: "Car setup",
    1: "Pits",
    2: "Damage",
    3: "Engine",
    4: "Temperatures",
    255: "MFD closed",
}

# Lap Valid Bit Flags
LAP_VALID_FLAGS = {
    0x01: "Lap valid",
    0x02: "Sector 1 valid",
    0x04: "Sector 2 valid",
    0x08: "Sector 3 valid",
}

# Wheel order for arrays
WHEEL_ORDER = {
    0: "Rear Left (RL)",
    1: "Rear Right (RR)",
    2: "Front Left (FL)",
    3: "Front Right (FR)",
}

# Temperature thresholds (approximate values for warnings)
TEMP_THRESHOLDS = {
    "engine_warning": 112,  # Celsius
    "engine_critical": 120,
    "brake_warning": 700,  # Celsius
    "brake_critical": 850,
    "tyre_warning": 105,  # Celsius
    "tyre_critical": 115,
}

# Speed conversion factors
SPEED_CONVERSIONS = {"kmh_to_mph": 0.621371, "ms_to_kmh": 3.6, "ms_to_mph": 2.23694}

# Distance conversion factors
DISTANCE_CONVERSIONS = {"m_to_km": 0.001, "m_to_miles": 0.000621371, "m_to_feet": 3.28084}
