from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Any
from datetime import datetime
import logging
import requests
import json

# Change to direct imports as modules are now at the same level in /app
import crud
import schemas
import models
import auth
import llm_utils
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    # dependencies=[Depends(auth.get_current_active_user)], # Apply dependency here if ALL routes need it
    responses={404: {"description": "Not found"}},
)

# --- Intent to Function Mapping (Conceptual) ---
# "create_reminder": crud.create_reminder (requires schemas.ReminderCreate)
# "create_task": crud.create_task (requires schemas.TaskCreate)
# "get_project_status": crud.get_project (requires project name/ID)
# "add_to_list": crud.add_item_to_list (requires schemas.ListItemCreate, list name/ID)
# "ask_general_question": Respond directly (Task 34)
# "general_greeting": Respond directly (Task 34)
# "unknown_or_malformed": Respond with clarification request (Task 34)
# "llm_api_error": Respond with error message (Task 34)
# "llm_parse_error": Respond with error message (Task 34)
# ... other intents ...
# -----------------------------------------------

@router.post("/message", response_model=schemas.ChatResponse)
def process_chat_message(
    message: schemas.ChatMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
) -> schemas.ChatResponse:
    """Receives a chat message, extracts intent/entities using LLM."""
    
    print(f"Received message: '{message.text}' from user: {current_user.email}")

    # Call the LLM utility function
    llm_result = llm_utils.extract_intent_entities(message.text)

    if not llm_result:
        # Handle cases where LLM call failed entirely (e.g., API key issue)
        # Raise an HTTPException for proper API error handling
        raise HTTPException(status_code=503, detail="LLM service unavailable or failed.")
        # Previous return: return {"error": "Failed to process message with LLM."}

    print(f"LLM Result: Intent='{llm_result.get('intent')}', Entities='{llm_result.get('entities')}'")

    intent = llm_result.get("intent")
    entities = llm_result.get("entities", {})

    # Initialize response components
    response_intent = intent if intent else "unknown"
    response_entities = entities
    response_message = "Sorry, I encountered an issue." # Default error message
    action_performed = False

    # --- Route based on intent --- 
    if intent == "create_reminder":
        logger.info(f"Routing to create_reminder with entities: {entities}")
        try:
            # Use description for reminder, consistent with schema
            description = entities.get("description") 
            iso_datetime_str = entities.get("trigger_datetime_iso")

            # Check for required fields
            if not description or not iso_datetime_str:
                logger.warning("Missing description or trigger_datetime_iso for create_reminder.")
                # Remove direct message setting, add error context to entities
                # response_message = "Sorry, I need both a description and a time to create a reminder." # noqa
                response_entities["error"] = "missing_required_entities"
                response_entities["missing"] = ["description", "trigger_datetime_iso"] # Be specific
            else:
                logger.debug(f"Attempting to parse ISO string: '{iso_datetime_str}'")
                try:
                    trigger_dt = datetime.fromisoformat(iso_datetime_str)
                    logger.debug(f"Successfully parsed datetime: {trigger_dt}")
                    if trigger_dt.tzinfo is None:
                         logger.warning(f"Parsed datetime {trigger_dt} is timezone-naive. Assuming UTC for now.")

                    reminder_in = schemas.ReminderCreate(
                        description=description, 
                        trigger_datetime=trigger_dt,
                        reminder_type=schemas.ReminderType.ONE_TIME, 
                    )
                    logger.debug("Calling create_user_reminder...")
                    created_reminder = crud.create_user_reminder(
                        db=db, reminder=reminder_in, owner_id=current_user.id
                    )
                    logger.debug("create_user_reminder successful.")
                    # Remove direct message setting, update entities with result
                    # response_message = f"OK. I've created reminder {created_reminder.id}: '{created_reminder.description}' due on {created_reminder.trigger_datetime.strftime('%Y-%m-%d %H:%M')}." # noqa
                    response_entities["created_reminder_id"] = created_reminder.id 
                    response_entities["created_description"] = created_reminder.description # Pass back info needed for response
                    response_entities["created_trigger_datetime"] = created_reminder.trigger_datetime.isoformat() # Pass back info needed for response
                    action_performed = True 
                except ValueError as ve: 
                    logger.error(f"ValueError caught during date parsing: {ve}", exc_info=True)
                    # Remove direct message setting, add error context to entities
                    # response_message = "Sorry, I couldn't understand the date/time for the reminder." # noqa
                    response_entities["error"] = "datetime_parse_error"
                    response_entities["value"] = iso_datetime_str # Include the value that failed
                except Exception as crud_err: 
                    logger.error(f"Error creating reminder in DB: {crud_err}", exc_info=True)
                    # Remove direct message setting, add error context to entities
                    # response_message = "Sorry, there was an issue saving the reminder."
                    response_entities["error"] = "database_error"
                    response_entities["operation"] = "create_reminder"

        except Exception as outer_err: 
             logger.error(f"Unexpected error processing create_reminder intent: {outer_err}", exc_info=True)
             # Remove direct message setting, add error context to entities
             # response_message = "Sorry, an unexpected error occurred while creating the reminder."
             response_entities["error"] = "unexpected_error"
             response_entities["intent_context"] = "create_reminder"

    elif intent == "create_task":
        logger.info(f"Routing to create_task with entities: {entities}")
        try:
            title = entities.get("title")
            if not title:
                 logger.warning("Missing title for create_task intent.")
                 # Remove direct message setting, add error context
                 # response_message = "Sorry, I need a title to create a task."
                 response_entities["error"] = "missing_required_entities"
                 response_entities["missing"] = ["title"]
            else:
                due_date_iso = entities.get("due_date_iso")
                due_date = None
                parsing_error = False
                if due_date_iso:
                    try:
                        due_date = datetime.fromisoformat(due_date_iso)
                        if due_date.tzinfo is None:
                            logger.warning(f"Parsed due_date {due_date} is timezone-naive. Assuming UTC for now.")
                    except ValueError:
                        logger.error(f"Failed to parse task due_date_iso: {due_date_iso}")
                        # Keep track of the parsing error for context, but don't set response_message yet
                        # response_message = "Warning: Could not understand the due date. Task created without it."
                        response_entities["warning"] = "datetime_parse_error" # Use warning key?
                        response_entities["value"] = due_date_iso
                        parsing_error = True 
                try:
                    task_data = schemas.TaskCreate(
                        title=title,
                        description=entities.get("description"),
                        due_date=None if parsing_error else due_date,
                    )
                    created_task = crud.create_user_task(
                        db=db, task=task_data, owner_id=current_user.id
                    )
                    # Remove direct message setting, update entities with result
                    # response_message = (response_message + " " + base_response) if parsing_error else base_response
                    response_entities["created_task_id"] = created_task.id
                    response_entities["created_title"] = created_task.title # Pass back info
                    response_entities["created_description"] = created_task.description # Pass back info
                    response_entities["created_due_date"] = created_task.due_date.isoformat() if created_task.due_date else None # Pass back info
                    # Keep parsing warning if it occurred
                    # response_entities["warning"] will persist if set above
                    action_performed = True
                except Exception as crud_err: 
                    logger.error(f"Error creating task in DB: {crud_err}", exc_info=True)
                    # Remove direct message setting, add error context
                    # response_message = "Sorry, there was an issue saving the task."
                    response_entities["error"] = "database_error"
                    response_entities["operation"] = "create_task"
        
        except Exception as outer_err: 
            logger.error(f"Unexpected error processing create_task intent: {outer_err}", exc_info=True)
            response_entities["error"] = "unexpected_error"
            response_entities["intent_context"] = "create_task"

    # --- Add handler for file summarization request --- 
    elif intent == "request_file_summary":
        logger.info(f"Routing to request_file_summary with entities: {entities}")
        file_id = entities.get("file_id")
        if not isinstance(file_id, int):
            logger.warning(f"Could not extract valid integer file_id from entities: {entities}")
            response_message = "Sorry, I couldn't understand which file ID you want to summarize."
            response_entities["error"] = "missing_or_invalid_entity"
            response_entities["expected_entity"] = "file_id (integer)"
        else:
            logger.info(f"Extracted file_id {file_id} for summarization. Calling internal API.")
            
            # --- Internal API Call to /files/{file_id}/summarize --- 
            summarize_url = f"http://localhost:8001/files/{file_id}/summarize" # Assuming same host/port
            # We need the user's token for the internal request
            # This assumes Request object is available via dependency injection
            # If not, alternative ways to get token might be needed.
            # **NOTE:** Requires `request: Request` in process_chat_message dependencies
            auth_header = request.headers.get('Authorization')
            headers = {'Authorization': auth_header if auth_header else ''}
            
            try:
                internal_response = requests.post(summarize_url, headers=headers)
                internal_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                
                summary_data = internal_response.json() # Parse JSON response
                
                # Update entities based on the summarization result
                if summary_data.get("error"):
                    response_entities["error"] = "summarization_failed"
                    response_entities["details"] = summary_data["error"]
                elif summary_data.get("summary"):
                    response_entities["summary"] = summary_data["summary"]
                    response_entities["summarized_file_id"] = file_id
                    action_performed = True # Mark action as successful
                else:
                    response_entities["error"] = "summarization_unexpected_response"
                    response_entities["details"] = "Summarization endpoint returned unexpected data."

            except requests.exceptions.RequestException as req_err:
                 logger.error(f"Internal API call to summarize failed: {req_err}", exc_info=True)
                 response_entities["error"] = "summarization_api_call_failed"
                 response_entities["details"] = str(req_err)
            except json.JSONDecodeError as json_err:
                 logger.error(f"Failed to decode JSON from summarize endpoint: {json_err}", exc_info=True)
                 response_entities["error"] = "summarization_bad_response_format"
                 response_entities["details"] = str(json_err)
            except Exception as e:
                 logger.error(f"Unexpected error during summarization call: {e}", exc_info=True)
                 response_entities["error"] = "summarization_unexpected_error"
                 response_entities["details"] = str(e)
            # --- End Internal API Call --- 

    # --- Add handler for file association request --- 
    elif intent == "associate_file":
        logger.info(f"Routing to associate_file with entities: {entities}")
        file_id = entities.get("file_id")
        target_type = entities.get("target_type")
        target_id = entities.get("target_id")

        # Validate extracted entities
        missing = []
        if not isinstance(file_id, int):
            missing.append("file_id (integer)")
        if target_type not in ["task", "project"]:
             missing.append("target_type ('task' or 'project')")
        if not isinstance(target_id, int):
            missing.append("target_id (integer)")

        if missing:
            logger.warning(f"Could not extract valid entities for associate_file: Missing {missing}")
            response_entities["error"] = "missing_or_invalid_entity"
            response_entities["missing"] = missing
            response_entities["details"] = "I need the file ID, the target type (task or project), and the target ID."
        else:
            logger.info(f"Extracted details for association: file={file_id}, target_type={target_type}, target_id={target_id}")
            
            # --- Call CRUD function --- 
            update_payload = schemas.FileReferenceUpdate(
                project_id=target_id if target_type == "project" else None,
                task_id=target_id if target_type == "task" else None
            )
            
            try:
                association_result = crud.update_file_reference_links(
                    db=db,
                    user_id=current_user.id,
                    file_id=file_id,
                    update_data=update_payload
                )
                
                # Handle CRUD result
                if isinstance(association_result, str): # Error code returned
                    if association_result == "unauthorized_file":
                         response_entities["error"] = "auth_error"
                         response_entities["details"] = "You don't own the file you're trying to associate."
                    elif association_result == "invalid_project":
                         response_entities["error"] = "invalid_target"
                         response_entities["details"] = f"Project ID {target_id} not found or you don't own it."
                    elif association_result == "invalid_task":
                         response_entities["error"] = "invalid_target"
                         response_entities["details"] = f"Task ID {target_id} not found or you don't own it."
                    else:
                         response_entities["error"] = "crud_error"
                         response_entities["details"] = f"Unknown CRUD error: {association_result}"
                elif association_result is None:
                    response_entities["error"] = "not_found"
                    response_entities["details"] = f"File ID {file_id} not found."
                else: # Success (association_result is the updated FileReference model)
                    logger.info(f"Successfully associated file {file_id} with {target_type} {target_id}")
                    action_performed = True # Mark action as successful
                    # Add context for response generation
                    response_entities["association_details"] = { 
                        "file_id": file_id,
                        "target_type": target_type,
                        "target_id": target_id,
                        "success": True,
                        # Ensure both keys always exist for consistent structure
                        "project_name": None, 
                        "task_title": None 
                    }
                    # Add linked item details if needed for response
                    if target_type == "project" and association_result.project:
                        response_entities["association_details"]["project_name"] = association_result.project.name
                    elif target_type == "task" and association_result.task:
                         response_entities["association_details"]["task_title"] = association_result.task.title
                         
            except Exception as e:
                logger.error(f"Unexpected error during file association CRUD call: {e}", exc_info=True)
                response_entities["error"] = "unexpected_error"
                response_entities["details"] = str(e)
            # --- End CRUD call --- 

    # --- Fallback for unhandled/general intents --- 
    if not action_performed and intent not in [
        "create_reminder", "create_task", "request_file_summary", "associate_file" # Add new intent
        ]: 
        logger.info(f"Intent '{intent}' has no specific action. Generating default response.")
        # No specific action needed, entities remain as extracted by LLM
        # generate_response_text will handle these cases

    # --- Construct Final Response --- 
    # Ensure this happens *after* all intent processing, using final state of variables
    logger.debug(f"Preparing final response. Intent: {response_intent}, Entities: {response_entities}")
    try:
        final_response_text = llm_utils.generate_response_text(response_intent, response_entities)
        api_response = schemas.ChatResponse(
            intent=response_intent,
            entities=response_entities,
            response_text=final_response_text
        )
        logger.debug(f"Final API response object created: {api_response}")
        return api_response
    except Exception as final_response_err:
        # Catch errors during final response generation itself
        logger.error(f"Failed to generate or construct final ChatResponse: {final_response_err}", exc_info=True)
        # Return a generic server error response that conforms to the model
        return schemas.ChatResponse(
            intent="internal_error",
            entities={"error": "Failed to construct final response"},
            response_text="Sorry, a critical error occurred while preparing the response."
        )

# The duplicate function definition below this comment needs to be removed.
# @router.post("/message", response_model=schemas.ChatResponse)
# def process_chat_message(...): 
#    ...

# Initial stub: Just return the raw LLM result for now
# Later (Task 33): Route based on intent
# Later (Task 34): Generate natural language response
# return llm_result # Return the dictionary from the LLM util 