import sys
import os
import logging

# Add the project root to the Python path to find zoltar_backend
# Assumes this script is run from the project root where zoltar_backend directory is located
project_root = os.path.abspath(os.path.dirname(__file__)) 
# If zoltar_backend is one level down from project_root:
zoltar_backend_path = os.path.join(project_root, 'zoltar_backend')
if zoltar_backend_path not in sys.path:
     # Adjust if your structure is different, find where 'file_utils.py' is relative to the script
     # If zoltar_backend is a sibling of this script's dir, use '..'
    sys.path.insert(0, project_root) # Add project root so 'from zoltar_backend...' works

try:
    from zoltar_backend.file_utils import extract_text_from_file
except ImportError:
    print("ERROR: Could not import 'extract_text_from_file'.")
    print("Ensure this script is run from the project root directory ('zoltar')")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)


# Configure basic logging to see output
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s') 

print("\n--- Testing TXT ---")
txt_content = extract_text_from_file("test_data/test.txt")
print(f"TXT Content Extracted:\n{txt_content}")

print("\n--- Testing PDF ---")
pdf_content = extract_text_from_file("test_data/test.pdf")
print(f"PDF Content Extracted:\n{pdf_content}")

print("\n--- Testing DOCX ---")
docx_content = extract_text_from_file("test_data/test.docx")
print(f"DOCX Content Extracted:\n{docx_content}")

print("\n--- Testing Non-existent file ---")
non_existent_content = extract_text_from_file("test_data/non_existent.txt")
print(f"Non-existent Content Extracted: {non_existent_content}")

print("\n--- Testing Unsupported file ---")
# Create a dummy unsupported file
try:
    with open("test_data/test.jpg", "w") as f: f.write("dummy") 
    unsupported_content = extract_text_from_file("test_data/test.jpg")
    print(f"Unsupported Content Extracted: {unsupported_content}")
finally:
    if os.path.exists("test_data/test.jpg"):
        os.remove("test_data/test.jpg") # Clean up dummy file

print("\n--- Test Complete ---") 