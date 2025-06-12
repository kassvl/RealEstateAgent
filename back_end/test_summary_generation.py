import os
import logging
from analyze_the_rooms import RoomAnalyzer # Assuming analyze_the_rooms.py is in the same directory or PYTHONPATH

# --- Mock Data for testing _generate_property_summary ---
MOCK_GEMINI_ANALYSIS_RESULTS_VALID = [
    {
        "image_url": "http://example.com/image1.jpg",
        "image_index": 0,
        "is_duplicate": False,
        "duplicate_of_index": None,
        "room_type_id": "living_room",
        "room_type_details": {"name": "Salon", "is_habitable": True},
        "identified_room_type_id": "living_room",
        "confidence_score": 0.9,
        "main_characteristics": ["Spacious", "Bright"],
        "potential_issues": [{"issue": "Slight wall scuff", "severity": "Low"}],
        "estimated_condition": "Good",
        "dominant_style_elements": ["Modern"],
        "lighting_quality": "Excellent",
        "renovation_need_impression": "Minor touch-ups",
        "is_likely_habitable": True,
        "additional_notes": "Pleasant room."
    },
    {
        "image_url": "http://example.com/image2.jpg",
        "image_index": 1,
        "is_duplicate": False,
        "duplicate_of_index": None,
        "room_type_id": "kitchen",
        "room_type_details": {"name": "Mutfak", "is_habitable": False},
        "identified_room_type_id": "kitchen",
        "confidence_score": 0.95,
        "main_characteristics": ["Modern appliances", "Island"],
        "potential_issues": [],
        "estimated_condition": "Very Good",
        "dominant_style_elements": ["Contemporary"],
        "lighting_quality": "Good",
        "renovation_need_impression": "None",
        "is_likely_habitable": True,
        "additional_notes": "Well-equipped kitchen."
    }
]

MOCK_GEMINI_ANALYSIS_RESULTS_WITH_ERROR = [
    {
        "image_url": "http://example.com/image1.jpg",
        "image_index": 0,
        "is_duplicate": False,
        "duplicate_of_index": None,
        "room_type_id": "living_room",
        "room_type_details": {"name": "Salon", "is_habitable": True},
        "identified_room_type_id": "living_room",
        "confidence_score": 0.9,
        "main_characteristics": ["Spacious", "Bright"],
        "potential_issues": [{"issue": "Slight wall scuff", "severity": "Low"}],
        "estimated_condition": "Good",
        "dominant_style_elements": ["Modern"],
        "lighting_quality": "Excellent",
        "renovation_need_impression": "Minor touch-ups",
        "is_likely_habitable": True,
        "additional_notes": "Pleasant room."
    },
    ["This is a list, not a dict, to trigger the error"], # Malformed entry
    {
        "image_url": "http://example.com/image3.jpg",
        "image_index": 2,
        "is_duplicate": False,
        "duplicate_of_index": None,
        "room_type_id": "bedroom",
        "room_type_details": {"name": "Yatak Odası", "is_habitable": True},
        "identified_room_type_id": "bedroom",
        "confidence_score": 0.85,
        "main_characteristics": ["Cozy", "Carpeted"],
        "potential_issues": [],
        "estimated_condition": "Good",
        "dominant_style_elements": ["Traditional"],
        "lighting_quality": "Average",
        "renovation_need_impression": "None",
        "is_likely_habitable": True,
        "additional_notes": "Comfortable bedroom."
    }
]
# --- End Mock Data ---

def setup_logging():
    # Configure logging to see DEBUG messages from RoomAnalyzer
    logger = logging.getLogger('analyze_the_rooms.RoomAnalyzer') # Get the specific logger
    logger.setLevel(logging.DEBUG) # Set it to DEBUG
    # Add a console handler if it doesn't have one
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
    # Configure root logger for general messages from this script
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def main():
    setup_logging()
    logging.info("🧪 Starting test for _generate_property_summary with mock data.")

    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logging.warning("GEMINI_API_KEY not set. Using a dummy key for RoomAnalyzer initialization.")
        logging.warning("The summary generation part of _generate_property_summary might fail if it attempts a real API call.")
        api_key = 'dummy_key_for_init_summary_test'

    analyzer = RoomAnalyzer(gemini_api_key=api_key) # Pass api_key with correct keyword and remove db_path

    # Test case 1: Valid mock data
    logging.info("\n--- Test Case 1: Valid Mock Data ---")
    try:
        summary_results_valid = analyzer._generate_property_summary(MOCK_GEMINI_ANALYSIS_RESULTS_VALID)
        logging.info("✔️ Summary generation with valid data successful.")
        if summary_results_valid:
            logging.info("Generated Summary (first 500 chars): %s...", str(summary_results_valid)[:500])
            if 'overall_property_summary' in summary_results_valid:
                logging.info("✔️ 'overall_property_summary' key found.")
            else:
                logging.warning("⚠️ 'overall_property_summary' key NOT found.")
        else:
            logging.info("ℹ️ Summary result with valid data is empty or None.")
    except Exception as e:
        logging.error(f"❌ An unexpected error occurred with valid data: {e}", exc_info=True)

    # Test case 2: Mock data with an error (item is a list)
    logging.info("\n--- Test Case 2: Error Mock Data (item is list) ---")
    try:
        summary_results_error = analyzer._generate_property_summary(MOCK_GEMINI_ANALYSIS_RESULTS_WITH_ERROR)
        logging.info("✔️ Summary generation with error data apparently successful (unexpected).")
        if summary_results_error:
            logging.info("Generated Summary (first 500 chars): %s...", str(summary_results_error)[:500])
        else:
            logging.info("ℹ️ Summary result with error data is empty or None.")
    except AttributeError as e:
        logging.error(f"❌ AttributeError caught with error data: {e}")
        logging.error("   This is the error we are trying to debug!")
    except Exception as e:
        logging.error(f"❌ An unexpected error occurred with error data: {e}", exc_info=True)

    logging.info("\n🏁 Finished all test cases for _generate_property_summary.")

if __name__ == '__main__':
    main()
