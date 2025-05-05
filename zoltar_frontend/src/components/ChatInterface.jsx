import React, { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios'; // Make sure axios is imported

const API_URL = 'http://localhost:8001'; // Use the correct backend port

function ChatInterface({ onLogout }) { // Receive onLogout prop
  const [messages, setMessages] = useState([]); // State to hold message objects {id, sender, text}
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false); // To disable input during API call
  const messagesEndRef = useRef(null); // Ref for scrolling to bottom
  const dropZoneRef = useRef(null); // Ref for the drop zone element
  const [isDragging, setIsDragging] = useState(false); // State for drag-and-drop

  // Function to handle sending a message
  const handleSendMessage = async (event) => {
    event.preventDefault();
    const messageText = inputText.trim();
    if (!messageText) return;

    console.log("Sending message:", messageText);
    setInputText(''); // Clear input immediately
    setIsLoading(true);

    // Add user message to state (Sub-task 35.6, but needed here)
    const userMessage = { id: Date.now(), sender: 'user', text: messageText };
    setMessages(prevMessages => [...prevMessages, userMessage]);

    // --- API Call Logic --- 
    const token = localStorage.getItem('authToken');
    if (!token) {
      console.error("No auth token found. Logging out.");
      alert("Authentication error. Please log in again."); // Simple user feedback
      onLogout(); // Trigger logout if token disappears
      setIsLoading(false);
      return;
    }

    try {
      const response = await axios.post(
        `${API_URL}/chat/message`, 
        { text: messageText }, // Request body
        { 
          headers: { 
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json' 
          } 
        }
      );
      
      console.log("Backend Response:", response.data);
      
      // --- Add bot response to messages state --- 
      if (response.data && response.data.response_text) {
          const botResponse = { 
              id: Date.now() + 1, // Simple ID generation, consider UUID later
              sender: 'bot', 
              text: response.data.response_text 
          };
          setMessages(prevMessages => [...prevMessages, botResponse]);
      } else {
          console.warn("Received response from backend without response_text:", response.data);
          // Optionally add a generic error message to the chat
      }
      // --- End bot response handling --- 
      
    } catch (error) {
      console.error("Error sending message:", error);
      let errorMessage = "Failed to send message.";
      if (error.response) {
        if (error.response.status === 401) {
          // Unauthorized - token might be expired/invalid
          console.error("Unauthorized. Token might be invalid. Logging out.");
          alert("Session expired or invalid. Please log in again.");
          onLogout();
          return; // Stop further processing
        } else {
           errorMessage = `Error: ${error.response.data.detail || error.response.statusText}`;
        }
      } else if (error.request) {
        errorMessage = "Error: Could not connect to the server.";
      } else {
        errorMessage = `Error: ${error.message}`;
      }
      // Display error to user (simple approach for now)
      // TODO: Add error message to chat display (Sub-task 35.6)
      alert(errorMessage);
      // Optionally, add the failed user message back to input?
      // setInputText(messageText);
    } finally {
      setIsLoading(false);
    }
    // --- End API Call Logic ---
  };

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // --- File Upload Handler (Sub-task 36.4) ---
  // DEFINE handleFileUpload BEFORE handleDrop because handleDrop depends on it
  const handleFileUpload = useCallback(async (files) => {
    if (!files || files.length === 0) {
      console.warn("handleFileUpload called with no files.");
      return;
    }

    // We'll just handle the first file for simplicity for now
    // TODO: Handle multiple file uploads later if needed
    const file = files[0]; 
    console.log(`Preparing to upload file: ${file.name} (${file.size} bytes)`);

    const formData = new FormData();
    formData.append("file", file); // The backend expects a field named "file"

    const token = localStorage.getItem('authToken');
    if (!token) {
      console.error("No auth token found for file upload. Logging out.");
      alert("Authentication error. Please log in again.");
      onLogout();
      return;
    }

    // Add a message to the chat indicating upload start (basic feedback)
    const uploadStartMessage = { 
      id: Date.now(), 
      sender: 'bot', 
      text: `Uploading ${file.name}...` 
    };
    setMessages(prevMessages => [...prevMessages, uploadStartMessage]);

    try {
      const response = await axios.post(
        `${API_URL}/files/upload`, // Target endpoint
        formData, // Send FormData
        { 
          headers: { 
            'Authorization': `Bearer ${token}`,
            // 'Content-Type': 'multipart/form-data' // Axios sets this automatically for FormData
          }, 
          // TODO: Add onUploadProgress handler later (Sub-task 36.6)
        }
      );

      console.log("File Upload Response:", response.data);

      // Add success message to chat (basic feedback)
      const successMessage = { 
        id: Date.now() + 1, 
        sender: 'bot', 
        text: `Successfully uploaded ${response.data.original_filename}. File ID: ${response.data.id}` 
      };
      // Update the messages state IMMUTABLY
      setMessages(prevMessages => prevMessages.map(msg => 
        msg.id === uploadStartMessage.id ? successMessage : msg
      )); // Replace the 'uploading' message

    } catch (error) {
      console.error("Error uploading file:", error);
      let errorMessage = "File upload failed.";
      if (error.response) {
        if (error.response.status === 401) {
          console.error("Unauthorized during file upload. Logging out.");
          alert("Session expired or invalid. Please log in again.");
          onLogout();
          return;
        }
        errorMessage = `Upload failed: ${error.response.data.detail || error.response.statusText}`;
      } else if (error.request) {
        errorMessage = "Upload failed: Could not connect to the server.";
      } else {
        errorMessage = `Upload failed: ${error.message}`;
      }

      // Add error message to chat (basic feedback)
      const failMessage = { 
        id: Date.now() + 1, 
        sender: 'bot', 
        text: errorMessage 
      };
      // Update the messages state IMMUTABLY
       setMessages(prevMessages => prevMessages.map(msg => 
        msg.id === uploadStartMessage.id ? failMessage : msg
      )); // Replace the 'uploading' message

    } 
  }, [onLogout, setMessages]); // Include dependencies: onLogout, setMessages
  // --- End File Upload Handler ---

  // --- Drag and Drop Handlers --- 
  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
    console.log("Drag Enter");
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    // Check if the leave event is heading outside the drop zone bounds
    // This prevents flickering when moving over child elements
    if (dropZoneRef.current && !dropZoneRef.current.contains(e.relatedTarget)) {
      setIsDragging(false);
      console.log("Drag Leave");
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault(); // Necessary to allow dropping
    e.stopPropagation();
    // You could add visual feedback here if needed during drag over
    // setIsDragging(true); // Ensure it stays true while dragging over
  }, []);

  // Define handleDrop AFTER handleFileUpload
  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    console.log("Drop Event");

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      // Sub-task 36.3: Handle the files by calling the upload function
      console.log("Files dropped: ", files);
      handleFileUpload(files); // Call upload function
    }
  }, [handleFileUpload]); // Add handleFileUpload to dependencies

  // Attach listeners to the drop zone element
  useEffect(() => {
    const dropZone = dropZoneRef.current;
    if (dropZone) {
      dropZone.addEventListener('dragenter', handleDragEnter);
      dropZone.addEventListener('dragleave', handleDragLeave);
      dropZone.addEventListener('dragover', handleDragOver);
      dropZone.addEventListener('drop', handleDrop);

      // Cleanup function
      return () => {
        dropZone.removeEventListener('dragenter', handleDragEnter);
        dropZone.removeEventListener('dragleave', handleDragLeave);
        dropZone.removeEventListener('dragover', handleDragOver);
        dropZone.removeEventListener('drop', handleDrop);
      };
    }
  // Correct dependencies for the effect hook
  }, [handleDragEnter, handleDragLeave, handleDragOver, handleDrop]); 

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    setMessages([]); // Clear messages on logout
    onLogout();
  };

  return (
    <div 
      ref={dropZoneRef} // Assign ref to the main container
      className={`flex flex-col h-screen bg-gray-100 p-4 
                  ${isDragging ? 'border-4 border-dashed border-blue-500 bg-blue-50' : 'border-transparent'}`}
    >
      <div className="chat-header">
        <h2>Chat</h2>
        <button onClick={handleLogout} className="logout-button">Logout</button>
      </div>
      <div className="messages-area">
        {messages.length === 0 && (
          <p className="no-messages">Send a message to start chatting with Zoltar.</p>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.sender}`}> {/* Style based on sender */}
            <p>{msg.text}</p>
          </div>
        ))}
        {/* Empty div to act as scroll target */}
        <div ref={messagesEndRef} />
      </div>
      <form className="message-input-form" onSubmit={handleSendMessage}>
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type your message or drop a file..."
          disabled={isLoading || !localStorage.getItem('authToken')}
          aria-label="Chat message input"
        />
        <button type="submit" disabled={isLoading || !inputText.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}

export default ChatInterface; 