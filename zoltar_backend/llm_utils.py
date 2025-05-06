import google.generativeai as genai
import os
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Configure the client. It will automatically pick up GOOGLE_API_KEY from env
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    # Check if API key was actually found
    if not os.getenv("GOOGLE_API_KEY"):
        logger.warning("GOOGLE_API_KEY environment variable not set. LLM calls will fail.")
except Exception as e:
    logger.error(f"Error configuring Google Generative AI: {e}")
    # Potentially raise the error or handle it based on application needs

# Specify the model - using the user-requested identifier
MODEL_NAME = "gemini-2.0-flash"

def create_structured_prompt(user_text: str) -> str:
    """Creates a prompt asking the LLM to extract intent and entities into JSON."""
    # Improved prompt for better JSON formatting and intent/entity identification
    # Added explicit instruction for ISO 8601 datetime parsing
    prompt = f"""
Analyze the following user request and identify the primary intent and any relevant entities. 
Return the result ONLY as a valid JSON object with two keys: "intent" (string) and "entities" (object). 

The "intent" should be a concise snake_case string representing the user's goal (e.g., "create_task", "get_project_summary", "set_reminder", "ask_general_question").

The "entities" object should contain key-value pairs for relevant information extracted from the text. Use snake_case for entity keys.

**Important:** If the user specifies a date and/or time, parse it and include it in the entities as a separate key (e.g., `trigger_datetime_iso`, `due_date_iso`) with the value formatted as a standard ISO 8601 string (YYYY-MM-DDTHH:MM:SS). If the year, date, or time part is ambiguous or missing, use reasonable defaults based on the current time, assuming the user means the near future. For example, "tomorrow 7pm" should be resolved to a full ISO string like "2024-08-16T19:00:00". "next Tuesday" should resolve to the upcoming Tuesday's date like "2024-08-20T00:00:00". Also include the original natural language description (e.g., `datetime_description`).

Examples:
User request: "Remind me to take out the trash tomorrow at 7pm"
Output: {{"intent": "create_reminder", "entities": {{"description": "Take out the trash", "datetime_description": "tomorrow at 7pm", "trigger_datetime_iso": "2024-08-16T19:00:00"}}}}

User request: "Set a task to finish the report by Friday"
Output: {{"intent": "create_task", "entities": {{"title": "finish the report", "datetime_description": "by Friday", "due_date_iso": "2024-08-16T23:59:59"}}}}

User request: "What is the status of the Project X?"
Output: {{"intent": "get_project_status", "entities": {{"project_name": "Project X"}}}}

User request: "Add milk and eggs to my grocery list"
Output: {{"intent": "add_to_list", "entities": {{"list_name": "grocery", "items": ["milk", "eggs"]}}}}

User request: "Upload the meeting notes file"
Output: {{"intent": "upload_file", "entities": {{"file_description": "meeting notes"}}}}

User request: "hello there"
Output: {{"intent": "general_greeting", "entities": {{}}}}

User request: "What's the capital of France?"
Output: {{"intent": "ask_general_question", "entities": {{"query": "What's the capital of France?"}}}}

User request: "summarize file ID 6"
Output: {{"intent": "request_file_summary", "entities": {{"file_id": 6}}}}

User request: "Can you give me a summary of file 12?"
Output: {{"intent": "request_file_summary", "entities": {{"file_id": 12}}}}

User request: "associate file 7 with task 15"
Output: {{"intent": "associate_file", "entities": {{"file_id": 7, "target_type": "task", "target_id": 15}}}}

User request: "link file id 3 to project 9"
Output: {{"intent": "associate_file", "entities": {{"file_id": 3, "target_type": "project", "target_id": 9}}}}

User request: "attach file 5 to the report task (ID 22)"
Output: {{"intent": "associate_file", "entities": {{"file_id": 5, "target_type": "task", "target_id": 22}}}}

---
User request: "{user_text}"
Output: 
"""
    return prompt

def extract_intent_entities(text: str) -> Optional[Dict[str, Any]]:
    """
    Sends text to the Gemini model to extract intent and entities.

    Args:
        text: The user's input text.

    Returns:
        A dictionary containing 'intent' and 'entities' if successful,
        None otherwise.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("LLM function called but GOOGLE_API_KEY is not set.")
        return None
        
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        prompt = create_structured_prompt(text)
        
        # Set generation config to force JSON output
        generation_config = genai.types.GenerationConfig(
            response_mime_type="application/json" 
        )
        
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )

        # Debug: Log raw response text
        logger.debug(f"Raw LLM Response Text: {response.text}")

        # The response text should be a JSON string already due to response_mime_type
        parsed_response = json.loads(response.text)
        
        # Basic validation of the expected structure
        if (isinstance(parsed_response, dict) and 
            "intent" in parsed_response and 
            "entities" in parsed_response and 
            isinstance(parsed_response["intent"], str) and 
            isinstance(parsed_response["entities"], dict)):
            logger.info(f"Successfully extracted intent: {parsed_response['intent']}")
            return parsed_response
        else:
            logger.warning(f"LLM response did not match expected JSON structure: {parsed_response}")
            # Fallback: Maybe treat as a general query?
            return {"intent": "unknown_or_malformed", "entities": {"raw_response": response.text}}
            
    except json.JSONDecodeError as json_err:
        logger.error(f"Failed to decode LLM JSON response: {json_err}")
        logger.error(f"LLM Raw Text was: {response.text if 'response' in locals() else 'N/A'}")
        return {"intent": "llm_parse_error", "entities": {"error": str(json_err), "raw_response": response.text if 'response' in locals() else 'N/A'}}
    except Exception as e:
        # Catch specific API errors if possible from the library
        logger.error(f"Error calling Gemini API: {e}", exc_info=True)
        # Check for specific google API errors if the library provides them
        # Example: if isinstance(e, google.api_core.exceptions.GoogleAPICallError): ...
        return {"intent": "llm_api_error", "entities": {"error": str(e)}}

def generate_response_text(intent: str, entities: dict, action_result: Any = None) -> str:
    """Generates a user-facing natural language response based on intent and action results.

    Args:
        intent: The detected intent (e.g., "create_reminder").
        entities: The extracted entities, potentially modified by the router with results/errors.
        action_result: The result from the executed CRUD action (e.g., the created reminder object, or None). - Deprecated: info now in entities

    Returns:
        A user-friendly string response.
    """
    logger.debug(f"Generating response for intent: {intent}, entities: {entities}")
    
    # Check for specific error flags first
    error_type = entities.get("error")
    if error_type == "missing_required_entities":
        missing_fields = entities.get("missing", [])
        # Add specific handling for create_reminder
        if intent == "create_reminder":
            needs_description = "description" in missing_fields
            needs_time = "trigger_datetime_iso" in missing_fields
            if needs_description and needs_time:
                return "Okay, what should I remind you about and when should I set the reminder?"
            elif needs_description:
                return "Okay, what is the description for this reminder?"
            elif needs_time:
                # Assume we got the description if only time is missing
                desc = entities.get("description", "this reminder") # Get original description if possible
                return f"Okay, I have the description '{desc}'. When should I remind you?"
            else:
                # Fallback if fields mismatch somehow
                return f"Sorry, I seem to be missing some details for the reminder ({', '.join(missing_fields)}). Could you provide those?"
        else:
            # Generic message for other intents
            return f"Sorry, I seem to be missing some details ({', '.join(missing_fields)}). Could you provide those?"
    if error_type == "datetime_parse_error":
        failed_value = entities.get("value", "the date/time")
        return f"Sorry, I couldn't understand '{failed_value}' as a valid date or time."
    if error_type == "database_error":
        operation = entities.get("operation", "save the data")
        return f"Sorry, there was an issue trying to {operation} in the database."
    if error_type == "unexpected_error":
        return "Sorry, an unexpected error occurred while processing your request."
    
    # Check for warnings (non-blocking errors)
    warning_type = entities.get("warning")
    warning_msg = ""
    if warning_type == "datetime_parse_error":
        failed_value = entities.get("value", "the date/time")
        warning_msg = f"(Warning: I couldn't understand '{failed_value}' as a date/time, so I proceeded without it.) "
        
    # --- Intent-specific success/fallback logic ---
    if intent == "create_reminder":
        created_id = entities.get("created_reminder_id")
        desc = entities.get("created_description")
        dt_iso = entities.get("created_trigger_datetime")
        if created_id and desc and dt_iso:
            try:
                dt_obj = datetime.fromisoformat(dt_iso)
                # Simple formatting, consider user preferences later
                formatted_dt = dt_obj.strftime('%Y-%m-%d %H:%M') 
                return f"OK. I've created reminder {created_id}: '{desc}' due on {formatted_dt}."
            except ValueError:
                 logger.error(f"Failed to re-parse created_trigger_datetime '{dt_iso}' for response.")
                 # Fallback if re-parsing fails (shouldn't happen)
                 return f"OK. I've created reminder {created_id}: '{desc}'."
        else:
            # If creation didn't happen (e.g., due to prior error caught above)
            return "Sorry, I wasn't able to create the reminder. Please try again or check the details."

    elif intent == "create_task":
        created_id = entities.get("created_task_id")
        title = entities.get("created_title")
        desc = entities.get("created_description")
        due_date_iso = entities.get("created_due_date")
        if created_id and title:
            base_response = f"OK. I've created task {created_id}: '{title}'."
            if desc:
                base_response += f" Description: '{desc}'."
            if due_date_iso:
                 try:
                     dt_obj = datetime.fromisoformat(due_date_iso)
                     formatted_dt = dt_obj.strftime('%Y-%m-%d %H:%M')
                     base_response += f" Due: {formatted_dt}."
                 except ValueError:
                     logger.error(f"Failed to re-parse created_due_date '{due_date_iso}' for response.")
            # Prepend warning if it exists
            return warning_msg + base_response
        else:
            # If creation didn't happen
            return warning_msg + "Sorry, I wasn't able to create the task. Please try again or check the details."

    elif intent == "ask_general_question":
        query = entities.get("query")
        if not query:
            return "It looks like you asked a question, but I couldn't figure out what it was. Could you rephrase?"
        # Call LLM again for the answer
        try:
            if not os.getenv("GOOGLE_API_KEY"):
                 logger.error("LLM API key not set, cannot answer general question.")
                 return "Sorry, I can't answer general questions right now due to a configuration issue."
                 
            model = genai.GenerativeModel(MODEL_NAME)
            # Simple prompt for answering
            response = model.generate_content(f"Answer the following question concisely: {query}")
            answer = response.text
            logger.info(f"Generated answer for general question: {answer[:100]}...")
            return answer
        except Exception as e:
            logger.error(f"Error calling Gemini API for general question: {e}", exc_info=True)
            return "Sorry, I encountered an error trying to answer your question."
            
    elif intent == "general_greeting":
        # Simple hardcoded response
        return "Hello there! How can I help you today?"

    elif intent == "llm_api_error":
        error_msg = entities.get('error', 'an unknown API error')
        return f"Sorry, I encountered an issue communicating with the language model ({error_msg}). Please try again later."
        
    elif intent == "llm_parse_error":
        return "Sorry, I received an unexpected response from the language model. Could you please rephrase your request?"
        
    elif intent == "unknown_or_malformed":
        return "Sorry, I'm not sure I understood that. Could you try rephrasing your request?"

    # --- Handle Summarization Results --- 
    elif intent == "request_file_summary":
        summarized_file_id = entities.get("summarized_file_id")
        summary = entities.get("summary")
        error_details = entities.get("details") # Check for specific errors passed from router
        error_type = entities.get("error") # Reuse existing error check
        
        if error_type:
            base_err_msg = f"Sorry, I couldn't summarize file {entities.get('file_id', 'the requested file')}."
            if error_type == "summarization_failed":
                 return f"{base_err_msg} Reason: {error_details or 'Unknown failure from summary endpoint.'}"
            elif error_type == "summarization_api_call_failed":
                 return f"{base_err_msg} Reason: Could not reach the summarization service."
            elif error_type in ["summarization_bad_response_format", "summarization_unexpected_response"]:
                 return f"{base_err_msg} Reason: Received an unexpected response from the summarization service."
            elif error_type == "summarization_unexpected_error":
                 return f"{base_err_msg} An unexpected internal error occurred."
            elif error_type == "missing_or_invalid_entity":
                return "Sorry, I couldn't understand which file ID you want to summarize. Please provide a valid number."
            else:
                # Fallback for other generic errors caught earlier
                return base_err_msg
        elif summarized_file_id and summary:
            return f"Here is the summary for file {summarized_file_id}:\n\n{summary}"
        else:
            # Should not happen if action_performed=True was set correctly in router
            return f"I understood you wanted to summarize file {entities.get('file_id', '...')}, but I don't have the result."

    # --- Handle File Association Results --- 
    elif intent == "associate_file":
        details = entities.get("association_details", {})
        error_type = entities.get("error")
        error_details = entities.get("details")
        file_id = details.get("file_id", "?")
        target_type = details.get("target_type", "?")
        target_id = details.get("target_id", "?")
        
        if error_type:
            base_err_msg = f"Sorry, I couldn't associate file {file_id} with {target_type} {target_id}."
            if error_type == "missing_or_invalid_entity":
                return f"Sorry, I'm missing some information. {error_details or 'Please specify the file ID, target type (task/project), and target ID.'}"
            elif error_type == "auth_error":
                return f"{base_err_msg} Reason: {error_details or 'Authorization failed.'}"
            elif error_type == "invalid_target":
                return f"{base_err_msg} Reason: {error_details or 'Target not found or invalid.'}"
            elif error_type == "not_found":
                return f"{base_err_msg} Reason: {error_details or 'File not found.'}"
            elif error_type == "crud_error":
                 return f"{base_err_msg} Reason: {error_details or 'Database error during association.'}"
            elif error_type == "unexpected_error":
                return f"{base_err_msg} Reason: An unexpected error occurred."
            else:
                return base_err_msg # Generic fallback
        elif details.get("success"):
            # Construct success message
            linked_name = None
            if target_type == "project":
                 linked_name = details.get("project_name")
            elif target_type == "task":
                 linked_name = details.get("task_title")
            
            if linked_name:
                 return f"OK. File {file_id} is now associated with {target_type} {target_id} ('{linked_name}')."
            else:
                 return f"OK. File {file_id} is now associated with {target_type} {target_id}."
        else:
             # Should not generally happen if logic is correct
             return f"I understood you wanted to associate file {file_id} with {target_type} {target_id}, but I couldn't confirm the result."

    else:
        # Default fallback for unhandled intents
        logger.warning(f"No specific response generation logic for intent: {intent}")
        return f"I understood your intent as '{intent}', but I don't have specific response logic for it yet."

# Example Usage (for testing purposes)
if __name__ == '__main__':
    # Ensure GOOGLE_API_KEY is set in your environment before running this
    if not os.getenv("GOOGLE_API_KEY"):
        print("Please set the GOOGLE_API_KEY environment variable to run this example.")
    else:
        test_text = "Remind me about the team sync tomorrow morning at 9am"
        print(f"Testing with: '{test_text}'")
        result = extract_intent_entities(test_text)
        print("Result:")
        print(json.dumps(result, indent=2))

        test_text_2 = "what is the weather like today?"
        print(f"\nTesting with: '{test_text_2}'")
        result_2 = extract_intent_entities(test_text_2)
        print("Result:")
        print(json.dumps(result_2, indent=2))

# --- Helper Function --- 
def summarize_text_gemini(text_to_summarize: str) -> Optional[str]:
    """Summarizes the given text using the configured Gemini model."""
    if not os.getenv("GOOGLE_API_KEY"):
        logger.error("Cannot summarize text: GOOGLE_API_KEY is not configured.")
        return None

    try:
        model = genai.GenerativeModel(MODEL_NAME)
        # Basic prompt - can be refined significantly
        prompt = f"Please provide a concise summary of the following meeting minutes:\n\n---\n{text_to_summarize}\n---\n\nSummary:"
        
        logger.debug(f"Sending text (first 100 chars: '{text_to_summarize[:100]}...') to Gemini model {MODEL_NAME} for summarization.")
        response = model.generate_content(prompt)
        
        # Simple error handling - check response structure as needed
        if response.parts:
            summary = response.text # Access the text part
            logger.info(f"Successfully generated summary using {MODEL_NAME}.")
            return summary
        else:
            # Log potential blocking or other issues
            logger.warning(f"Gemini response did not contain expected text part. Response: {response}")
            # Check for finish_reason if needed: response.prompt_feedback.block_reason
            return None

    except Exception as e:
        logger.error(f"Error calling Gemini API ({MODEL_NAME}) for summarization: {e}", exc_info=True)
        return None

# --- (Optional) Add other LLM utility functions here later --- 