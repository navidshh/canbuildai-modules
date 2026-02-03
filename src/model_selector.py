"""
Model selector utility to dynamically choose the correct trained model
based on building type and location.
"""

# Mapping of (building_type, location) -> config_file
MODEL_CONFIG_MAP = {
    ("MidriseApartment", "Toronto"): "input_config_midrise_toronto.yml",
    ("Lowrise", "Toronto"): "input_config_lowrise_toronto.yml",
    # Add more mappings as you add more trained models:
    # ("HighriseApartment", "Toronto"): "input_config_highrise_toronto.yml",
    # ("MidriseApartment", "Calgary"): "input_config_midrise_calgary.yml",
}

# Default fallback if no exact match
DEFAULT_CONFIG = "input_config_midrise_toronto.yml"


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
    
    # Try exact match
    key = (building_type, location)
    if key in MODEL_CONFIG_MAP:
        return MODEL_CONFIG_MAP[key]
    
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
    for (building_type, location) in MODEL_CONFIG_MAP.keys():
        if location not in supported:
            supported[location] = []
        supported[location].append(building_type)
    
    return supported
