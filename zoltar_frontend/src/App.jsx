import React, { useState, useEffect } from 'react'
import Login from './components/Login'
import ChatInterface from './components/ChatInterface'
import './App.css'

function App() {
  // Check for token in localStorage initially
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('authToken'))

  // Function to handle successful login (passed to Login component)
  const handleLogin = () => {
    console.log("Handling login in App.jsx")
    setIsAuthenticated(true)
  }

  // Function to handle logout
  const handleLogout = () => {
    console.log("Handling logout in App.jsx")
    localStorage.removeItem('authToken') // Remove token
    setIsAuthenticated(false)
  }

  // Effect to check token validity on load (optional, advanced)
  // For now, just checking presence is enough for basic state
  useEffect(() => {
    const token = localStorage.getItem('authToken')
    // TODO: Optionally add a check here to call a backend /users/me endpoint
    // to verify the token is still valid before setting isAuthenticated
    setIsAuthenticated(!!token)
  }, []) // Empty dependency array means run once on mount

  return (
    <div className="App">
      <h1>Zoltar Assistant</h1>
      {isAuthenticated ? (
        // Render ChatInterface when authenticated, passing handleLogout
        <ChatInterface onLogout={handleLogout} />
      ) : (
        // Render Login component when not authenticated
        <Login onLoginSuccess={handleLogin} />
      )}
    </div>
  )
}

export default App
