import logging
import os
from typing import Optional
from pathlib import Path

# Import specific libraries for file types
from pypdf import PdfReader
from docx import Document

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx"}

def extract_text_from_file(file_path: str) -> Optional[str]:
    """Extracts text content from supported file types (txt, pdf, docx).

    Args:
        file_path: The absolute or relative path to the file.

    Returns:
        The extracted text content as a string, or None if the file is 
        not found, not supported, or extraction fails.
    """
    logger.info(f"Attempting to extract text from: {file_path}")
    path = Path(file_path)
    
    if not path.is_file():
        logger.error(f"File not found at path: {file_path}")
        return None

    file_extension = path.suffix.lower()

    if file_extension not in SUPPORTED_EXTENSIONS:
        logger.warning(f"Unsupported file type for text extraction: {file_extension}")
        return None

    try:
        if file_extension == ".txt":
            # Try common encodings
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except UnicodeDecodeError:
                logger.warning(f"UTF-8 decoding failed for {file_path}, trying latin-1.")
                with open(path, 'r', encoding='latin-1') as f:
                    text = f.read()
            logger.info(f"Successfully extracted text from TXT file: {file_path}")
            return text

        elif file_extension == ".pdf":
            reader = PdfReader(path)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n" # Add newline between pages
            logger.info(f"Successfully extracted text from PDF file: {file_path} ({len(reader.pages)} pages)")
            return text

        elif file_extension == ".docx":
            document = Document(path)
            text = "\n".join([para.text for para in document.paragraphs])
            logger.info(f"Successfully extracted text from DOCX file: {file_path}")
            return text

    except Exception as e:
        logger.error(f"Error extracting text from {file_path} (type: {file_extension}): {e}", exc_info=True)
        return None

    # Should not be reached if extension is supported
    return None 