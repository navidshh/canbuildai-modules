"""
Model selector utility to dynamically choose the correct trained model
based on building type and location.
"""

# Mapping of training model directories to (building_type, location)
# Format: "training_model_<timestamp> - <BuildingType> - <City>"
TRAINING_MODEL_DIRS = {
    # Calgary
    ("HighRise", "Calgary"): "training_model_2025-03-19 08-57-03.416313 - Highrise - Calgary",
    ("LargeOffice", "Calgary"): "training_model_2025-03-19 09-23-13.973331 - LargeOffice - Calgary",
    ("LowRise", "Calgary"): "training_model_2025-03-19 10-06-35.298415 - LowRise - Calgary",
    ("MediumOffice", "Calgary"): "training_model_2025-03-19 10-20-29.023979 - MediumOffice - Calgary",
    ("MidRise", "Calgary"): "training_model_2025-03-19 10-55-28.424891 - MidRise - Calgary",
    ("SmallOffice", "Calgary"): "training_model_2025-03-19 11-08-48.674609 - SmallOffice - Calgary",
    
    # Halifax
    ("HighRise", "Halifax"): "training_model_2025-03-19 15-04-32.945649 - HighRise - Halifax",
    ("LargeOffice", "Halifax"): "training_model_2025-03-19 15-26-40.240822 - LargeOffice - Halifax",
    ("LowRise", "Halifax"): "training_model_2025-03-19 15-54-38.519386 - LowRise - Halifax",
    ("MediumOffice", "Halifax"): "training_model_2025-03-20 08-30-26.859352 - MediumOffice - Halifax",
    ("MidRise", "Halifax"): "training_model_2025-03-20 08-57-16.737131 - MidRise - Halifax",
    ("SmallOffice", "Halifax"): "training_model_2025-03-20 09-19-06.163289 - SmallOffice - Halifax",
    
    # Montreal
    ("HighRise", "Montreal"): "training_model_2025-03-20 10-00-45.712085 - HighRise - Montreal",
    ("LargeOffice", "Montreal"): "training_model_2025-03-20 10-09-07.224874 - LargeOffice - Montreal",
    ("LowRise", "Montreal"): "training_model_2025-03-20 10-57-23.825582 - LowRise - Montreal",
    ("MediumOffice", "Montreal"): "training_model_2025-03-20 11-15-01.623691 - MediumOffice - Montreal",
    ("MidRise", "Montreal"): "training_model_2025-03-20 12-35-20.761539 - MidRise - Montreal",
    ("SmallOffice", "Montreal"): "training_model_2025-03-20 12-44-48.193300 - SmallOffice - Montreal",
    
    # Iqaluit
    ("HighRise", "Iqaluit"): "training_model_2025-03-20 13-25-38.205812 - HighRise - Iqaluit",
    ("LargeOffice", "Iqaluit"): "training_model_2025-03-20 13-32-56.926225 - LargeOffice - Iqaluit",
    ("LowRise", "Iqaluit"): "training_model_2025-03-20 14-13-54.240044 - LowRise - Iqaluit",
    ("MediumOffice", "Iqaluit"): "training_model_2025-03-20 14-20-58.003754 - MediumOffice - Iqaluit",
    ("MidRise", "Iqaluit"): "training_model_2025-03-20 15-04-05.433414 - MidRise - Iqaluit",
    ("SmallOffice", "Iqaluit"): "training_model_2025-03-20 15-15-24.992153 - SmallOffice - Iqaluit",
    
    # Toronto
    ("HighRise", "Toronto"): "training_model_2025-03-21 14-22-11.736787 - HighRise - Toronto",
    ("LargeOffice", "Toronto"): "training_model_2025-03-21 14-48-01.109426 - LargeOffice - Toronto",
    ("LowRise", "Toronto"): "training_model_2025-03-21 15-16-19.288272 - Lowrise - Toronto",
    ("MediumOffice", "Toronto"): "training_model_2025-03-21 15-39-23.554654 - MediumOffice - Toronto",
    ("MidRise", "Toronto"): "training_model_2025-03-24 09-36-33.111622 - MidRise - Toronto",
    ("SmallOffice", "Toronto"): "training_model_2025-03-24 09-50-49.528457 - SmallOffice - Toronto",
    
    # Vancouver
    ("HighRise", "Vancouver"): "training_model_2025-03-24 10-22-46.475366 - HighRise - Vancouver",
    ("LargeOffice", "Vancouver"): "training_model_2025-03-24 10-56-15.604135 - LargeOffice - Vancouver",
    ("LowRise", "Vancouver"): "training_model_2025-03-24 11-22-44.767301 - LowRise - Vancouver",
    ("MediumOffice", "Vancouver"): "training_model_2025-03-24 12-00-25.685860 - MediumOffice - Vancouver",
    ("MidRise", "Vancouver"): "training_model_2025-03-24 12-07-39.982111 - MidRise - Vancouver",
    ("SmallOffice", "Vancouver"): "training_model_2025-03-24 12-37-33.522006 - SmallOffice - Vancouver",
    
    # Whitehorse
    ("HighRise", "Whitehorse"): "training_model_2025-03-24 13-06-11.451567 - HighRise - Whitehorse",
    ("LargeOffice", "Whitehorse"): "training_model_2025-03-24 13-54-31.065170 - LargeOffice - Whitehorse",
    ("LowRise", "Whitehorse"): "training_model_2025-03-24 14-03-20.048528 - LowRise - Whitehorse",
    ("MediumOffice", "Whitehorse"): "training_model_2025-03-24 14-59-59.300675 - MediumOffice - Whitehorse",
    ("MidRise", "Whitehorse"): "training_model_2025-03-24 15-19-57.897188 - MidRise - Whitehorse",
    ("SmallOffice", "Whitehorse"): "training_model_2025-03-24 15-48-07.257346 - SmallOffice - Whitehorse",
    
    # Winnipeg
    ("HighRise", "Winnipeg"): "training_model_2025-03-25 08-25-03.069892 - HighRise - Winnipeg",
    ("LargeOffice", "Winnipeg"): "training_model_2025-03-25 08-58-52.965988 - LargeOffice - Winnipeg",
    ("LowRise", "Winnipeg"): "training_model_2025-03-25 09-06-30.330159 - LowRise - Winnipeg",
    ("MediumOffice", "Winnipeg"): "training_model_2025-03-25 09-48-30.480694 - MediumOffice - Winnipeg",
    ("MidRise", "Winnipeg"): "training_model_2025-03-25 09-56-57.950580 - MidRise -Winnipeg",
    ("SmallOffice", "Winnipeg"): "training_model_2025-03-25 10-45-10.525416 - SmallOffice - Winnipeg",
}

# Mapping for legacy building type names (for backward compatibility)
BUILDING_TYPE_ALIASES = {
    "MidriseApartment": "MidRise",
    "Lowrise": "LowRise",
    "HighriseApartment": "HighRise",
    "Highrise": "HighRise",
    "Midrise": "MidRise",
    "LargeOffice": "LargeOffice",
    "MediumOffice": "MediumOffice",
    "SmallOffice": "SmallOffice",
}

# Mapping of (building_type, location) -> config_file
MODEL_CONFIG_MAP = {
    ("MidriseApartment", "Toronto"): "input_config_midrise_toronto.yml",
    ("Lowrise", "Toronto"): "input_config_lowrise_toronto.yml",
    # Note: Legacy mapping for backward compatibility
}

# Default fallback if no exact match
DEFAULT_CONFIG = "input_config_midrise_toronto.yml"


def get_training_model_dir(building_type: str, location: str) -> str:
    """
    Returns the training model directory based on building type and location.
    
    Args:
        building_type: The building type (e.g., "HighRise", "LowRise", "MediumOffice")
        location: The location (e.g., "Toronto", "Calgary")
        
    Returns:
        Training model directory name
    """
    # Normalize inputs
    building_type = building_type.strip()
    location = location.strip()
    
    # Apply alias mapping if building_type is a legacy name
    if building_type in BUILDING_TYPE_ALIASES:
        building_type = BUILDING_TYPE_ALIASES[building_type]
    
    # Try exact match
    key = (building_type, location)
    if key in TRAINING_MODEL_DIRS:
        return TRAINING_MODEL_DIRS[key]
    
    # Try case-insensitive match
    key_lower = (building_type.lower(), location.lower())
    for (bt, loc), dir_name in TRAINING_MODEL_DIRS.items():
        if bt.lower() == key_lower[0] and loc.lower() == key_lower[1]:
            return dir_name
    
    # No match found
    raise ValueError(f"No training model found for {building_type} in {location}")


def get_config_for_model(building_type: str, location: str) -> str:
    """
    Returns the appropriate config file name based on building type and location.
    
    Args:
        building_type: The building type (e.g., "MidriseApartment", "Lowrise")
        location: The location (e.g., "Toronto", "Calgary")
        
    Returns:
        Config file name (e.g., "input_config_midrise_toronto.yml")
    """
    # Normalize inputs
    building_type = building_type.strip()
    location = location.strip()
    
    # Try exact match in legacy mapping
    key = (building_type, location)
    if key in MODEL_CONFIG_MAP:
        return MODEL_CONFIG_MAP[key]
    
    # Generate dynamic config file name based on training model directory
    try:
        training_dir = get_training_model_dir(building_type, location)
        # For now, use the default config as base
        # In the future, you can generate configs dynamically based on training_dir
        return DEFAULT_CONFIG
    except ValueError:
        pass
    
    # Fallback to default
    print(f"Warning: No specific model found for {building_type} in {location}. Using default model.")
    return DEFAULT_CONFIG


def extract_location_from_epw(epw_file: str) -> str:
    """
    Extract location name from EPW file name.
    Example: "CAN_ON_Toronto.Pearson.Intl.AP.716240_CWEC2016.epw" -> "Toronto"
    
    Args:
        epw_file: EPW file name
        
    Returns:
        Location name
    """
    if not epw_file:
        return "Unknown"
    
    # Remove CAN_ prefix and file extension
    location = epw_file.replace("CAN_", "").replace(".epw", "")
    
    # Common patterns:
    # CAN_ON_Toronto.Pearson.Intl.AP.716240_CWEC2016.epw -> ON_Toronto
    # Extract the city name (usually after the province code)
    parts = location.split("_")
    if len(parts) >= 2:
        # parts[0] is province code (ON, BC, etc)
        # parts[1] is city name
        city = parts[1].split(".")[0]  # Get first part before any dots
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
        if location not in supported:
            supported[location] = []
        supported[location].append(building_type)
    
    return supported


def list_all_supported_combinations() -> list:
    """
    Returns a list of all supported (building_type, location) combinations.
    
    Returns:
        List of tuples: [(building_type, location), ...]
    """
    return list(TRAINING_MODEL_DIRS.keys())
