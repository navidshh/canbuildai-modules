"""
Model selector utility to dynamically choose the correct trained model
based on building type and location.
"""

# Mapping of (canonical_building_type, location) -> training_model directory name on disk.
# Folder names must match exactly what exists under canbuildai-modules/input/.
TRAINING_MODEL_DIRS = {
    # Calgary
    ("HighRise",     "Calgary"): "training_model_2025-03-19 08-57-03.416313 - Calgary Highrise",
    ("LargeOffice",  "Calgary"): "training_model_2025-03-19 09-23-13.973331 - Calgary Large Office",
    ("LowRise",      "Calgary"): "training_model_2025-03-19 10-06-35.298415 - Calgary Lowrise",
    ("MediumOffice", "Calgary"): "training_model_2025-03-19 10-20-29.023979 - Calgary Medium Office",
    ("MidRise",      "Calgary"): "training_model_2025-03-19 10-55-28.424891 - Calgary Midrise",
    ("SmallOffice",  "Calgary"): "training_model_2025-03-19 11-08-48.674609 - Calgary Small Office",

    # Halifax
    ("HighRise",     "Halifax"): "training_model_2025-03-19 15-04-32.945649 - Halifax Highrise",
    ("LargeOffice",  "Halifax"): "training_model_2025-03-19 15-26-40.240822 - Halifax Large Office",
    ("LowRise",      "Halifax"): "training_model_2025-03-19 15-54-38.519386 - Halifax Lowrise",
    ("MediumOffice", "Halifax"): "training_model_2025-03-20 08-30-26.859352 - Halifax Medium Office",
    ("MidRise",      "Halifax"): "training_model_2025-03-20 08-57-16.737131 - Halifax Midrise",
    ("SmallOffice",  "Halifax"): "training_model_2025-03-20 09-19-06.163289 - Halifax Small Office",

    # Montreal
    ("HighRise",     "Montreal"): "training_model_2025-03-20 10-00-45.712085 - Montreal Highrise",
    ("LargeOffice",  "Montreal"): "training_model_2025-03-20 10-09-07.224874 - Montreal Large Office",
    ("LowRise",      "Montreal"): "training_model_2025-03-20 10-57-23.825582 - Montreal Lowrise",
    ("MediumOffice", "Montreal"): "training_model_2025-03-20 11-15-01.623691 - Montreal Medium Office",
    ("MidRise",      "Montreal"): "training_model_2025-03-20 12-35-20.761539 - Montreal Midrise",
    ("SmallOffice",  "Montreal"): "training_model_2025-03-20 12-44-48.193300 - Montreal Small Office",

    # Iqaluit  (note: lowrise folder has a double space before "Iqaluit")
    ("HighRise",     "Iqaluit"): "training_model_2025-03-20 13-25-38.205812 - Iqaluit Highrise",
    ("LargeOffice",  "Iqaluit"): "training_model_2025-03-20 13-32-56.926225 - Iqaluit Large Office",
    ("LowRise",      "Iqaluit"): "training_model_2025-03-20 14-13-54.240044 -  Iqaluit Lowrise",
    ("MediumOffice", "Iqaluit"): "training_model_2025-03-20 14-20-58.003754 - Iqaluit Medium Office",
    ("MidRise",      "Iqaluit"): "training_model_2025-03-20 15-04-05.433414 - Iqaluit Midrise",
    ("SmallOffice",  "Iqaluit"): "training_model_2025-03-20 15-15-24.992153 - Iqaluit Small Office",

    # Toronto
    ("HighRise",     "Toronto"): "training_model_2025-03-21 14-22-11.736787 - Toronto Highrise",
    ("LargeOffice",  "Toronto"): "training_model_2025-03-21 14-48-01.109426 - Toronto Large Office",
    ("LowRise",      "Toronto"): "training_model_2025-03-21 15-16-19.288272 - Toronto Lowrise",
    ("MediumOffice", "Toronto"): "training_model_2025-03-21 15-39-23.554654 - Toronto Medium Office",
    ("MidRise",      "Toronto"): "training_model_2025-03-24 09-36-33.111622 - Toronto Midrise",
    ("SmallOffice",  "Toronto"): "training_model_2025-03-24 09-50-49.528457 - Toronto Small Office",

    # Vancouver
    ("HighRise",     "Vancouver"): "training_model_2025-03-24 10-22-46.475366 - Vancouver Highrise",
    ("LargeOffice",  "Vancouver"): "training_model_2025-03-24 10-56-15.604135 - Vancouver Large Office",
    ("LowRise",      "Vancouver"): "training_model_2025-03-24 11-22-44.767301 - Vancouver Lowrise",
    ("MediumOffice", "Vancouver"): "training_model_2025-03-24 12-00-25.685860 - Vancouver Medium Office",
    ("MidRise",      "Vancouver"): "training_model_2025-03-24 12-07-39.982111 - Vancouver Midrise",
    ("SmallOffice",  "Vancouver"): "training_model_2025-03-24 12-37-33.522006 - Vancouver Small Office",

    # Winnipeg
    ("HighRise",     "Winnipeg"): "training_model_2025-03-25 08-25-03.069892 - Winnipeg Highrise",
    ("LargeOffice",  "Winnipeg"): "training_model_2025-03-25 08-58-52.965988 - Winnipeg Large Office",
    ("LowRise",      "Winnipeg"): "training_model_2025-03-25 09-06-30.330159 - Winnipeg Lowrise",
    ("MediumOffice", "Winnipeg"): "training_model_2025-03-25 09-48-30.480694 - Winnipeg Medium Office",
    ("MidRise",      "Winnipeg"): "training_model_2025-03-25 09-56-57.950580 - Winnipeg Midrise",
    ("SmallOffice",  "Winnipeg"): "training_model_2025-03-25 10-45-10.525416 - Winnipeg Small Office",
}

# Aliases that translate any legacy / variant building-type spelling to the canonical key used above.
BUILDING_TYPE_ALIASES = {
    # Canonical (identity mappings, for safety)
    "HighRise":     "HighRise",
    "MidRise":      "MidRise",
    "LowRise":      "LowRise",
    "LargeOffice":  "LargeOffice",
    "MediumOffice": "MediumOffice",
    "SmallOffice":  "SmallOffice",
    # Legacy / alternate spellings
    "HighriseApartment": "HighRise",
    "MidriseApartment":  "MidRise",
    "LowriseApartment":  "LowRise",
    "Highrise":          "HighRise",
    "Midrise":           "MidRise",
    "Lowrise":           "LowRise",
    "highrise":          "HighRise",
    "midrise":           "MidRise",
    "lowrise":           "LowRise",
    "Large Office":      "LargeOffice",
    "Medium Office":     "MediumOffice",
    "Small Office":      "SmallOffice",
}

# Aliases that translate any extracted location string to the canonical city key used above.
LOCATION_ALIASES = {
    "Calgary":   "Calgary",
    "Halifax":   "Halifax",
    "Montreal":  "Montreal",
    "Iqaluit":   "Iqaluit",
    "Toronto":   "Toronto",
    "Vancouver": "Vancouver",
    "Winnipeg":  "Winnipeg",
}


def _canonical_building_type(building_type: str) -> str:
    """Return the canonical building-type key, applying aliases if necessary."""
    if not building_type:
        return ""
    bt = building_type.strip()
    return BUILDING_TYPE_ALIASES.get(bt, bt)


def _canonical_location(location: str) -> str:
    """Return the canonical city key, applying aliases if necessary."""
    if not location:
        return ""
    loc = location.strip()
    return LOCATION_ALIASES.get(loc, loc)


def _config_filename_for(building_type: str, location: str) -> str:
    """Build the conventional YAML config filename: input_config_<arch>_<city>.yml (all lowercase)."""
    bt_slug = building_type.lower()
    city_slug = location.lower()
    return f"input_config_{bt_slug}_{city_slug}.yml"


# Mapping of (canonical_building_type, location) -> config_file, derived from TRAINING_MODEL_DIRS.
MODEL_CONFIG_MAP = {
    key: _config_filename_for(bt, loc)
    for key in TRAINING_MODEL_DIRS
    for bt, loc in [key]
}

# Default fallback if no exact match is found.
DEFAULT_CONFIG = "input_config_midrise_toronto.yml"


def get_training_model_dir(building_type: str, location: str) -> str:
    """
    Returns the training model directory name based on building type and location.

    Args:
        building_type: The building type (e.g., "HighRise", "LowRise", "MediumOffice")
        location: The location (e.g., "Toronto", "Calgary")

    Returns:
        Training model directory name (matches an actual folder under input/).

    Raises:
        ValueError: if no model is registered for the given combination.
    """
    bt = _canonical_building_type(building_type)
    loc = _canonical_location(location)

    key = (bt, loc)
    if key in TRAINING_MODEL_DIRS:
        return TRAINING_MODEL_DIRS[key]

    # Case-insensitive fallback
    for (k_bt, k_loc), dir_name in TRAINING_MODEL_DIRS.items():
        if k_bt.lower() == bt.lower() and k_loc.lower() == loc.lower():
            return dir_name

    raise ValueError(f"No training model found for {building_type!r} in {location!r}")


def get_config_for_model(building_type: str, location: str) -> str:
    """
    Returns the appropriate config file name based on building type and location.

    Args:
        building_type: The building type (e.g., "MidRise", "LowRise", "LargeOffice").
                       Legacy spellings (e.g. "MidriseApartment") are accepted via aliases.
        location: The location (e.g., "Toronto", "Calgary").

    Returns:
        Config file name (e.g., "input_config_midrise_toronto.yml"). Falls back to
        DEFAULT_CONFIG (with a warning) if the combination is not registered.
    """
    bt = _canonical_building_type(building_type)
    loc = _canonical_location(location)

    key = (bt, loc)
    if key in MODEL_CONFIG_MAP:
        return MODEL_CONFIG_MAP[key]

    # Case-insensitive fallback
    for (k_bt, k_loc), cfg_name in MODEL_CONFIG_MAP.items():
        if k_bt.lower() == bt.lower() and k_loc.lower() == loc.lower():
            return cfg_name

    print(f"Warning: No specific model found for {building_type!r} in {location!r}. Using default model.")
    return DEFAULT_CONFIG


def extract_location_from_epw(epw_file: str) -> str:
    """
    Extract location name from EPW file name.

    Examples:
        "CAN_ON_Toronto.Pearson.Intl.AP.716240_CWEC2016.epw"        -> "Toronto"
        "CAN_QC_Montreal-Trudeau.Intl.AP.716270_CWEC2016.epw"       -> "Montreal"
        "CAN_MB_Winnipeg-Richardson.Intl.AP.718520_CWEC2016.epw"    -> "Winnipeg"

    Args:
        epw_file: EPW file name

    Returns:
        Location name (city), or "Unknown" if it cannot be parsed.
    """
    if not epw_file:
        return "Unknown"

    # Strip the CAN_ prefix and .epw suffix
    trimmed = epw_file.replace("CAN_", "").replace(".epw", "")

    # Format: <PROV>_<City...>_<...>
    parts = trimmed.split("_")
    if len(parts) >= 2:
        # parts[0] = province code (ON, BC, ...)
        # parts[1] = city segment, possibly hyphenated and dot-suffixed
        city_segment = parts[1].split(".")[0]   # drop ".Pearson.Intl..."
        city = city_segment.split("-")[0]       # drop "-Trudeau", "-Richardson", etc.
        return city

    return "Unknown"


def get_supported_models() -> dict:
    """
    Returns a dictionary of all supported building type and location combinations.

    Returns:
        Dictionary with structure: {location: [building_types]}
    """
    supported = {}
    for (building_type, location) in TRAINING_MODEL_DIRS.keys():
        supported.setdefault(location, []).append(building_type)
    return supported


def list_all_supported_combinations() -> list:
    """
    Returns a list of all supported (building_type, location) combinations.

    Returns:
        List of tuples: [(building_type, location), ...]
    """
    return list(TRAINING_MODEL_DIRS.keys())
