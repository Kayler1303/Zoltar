import React, { useState } from 'react';
import axios from 'axios'; // Import axios

// Assuming backend runs on localhost:8000
const API_URL = 'http://localhost:8001'; // Use the correct backend port

function Login({ onLoginSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError(''); // Clear previous errors
    setLoading(true);

    // Data needs to be sent as x-www-form-urlencoded for FastAPI's OAuth2PasswordRequestForm
    const loginData = new URLSearchParams();
    loginData.append('username', email); // FastAPI OAuth2 form uses 'username' field for email
    loginData.append('password', password);

    try {
      const response = await axios.post(`${API_URL}/token`, loginData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      });

      if (response.data.access_token) {
        console.log("Login successful, token received:", response.data.access_token);
        // Store the token (e.g., in localStorage)
        localStorage.setItem('authToken', response.data.access_token);
        // Notify parent component of successful login
        if (onLoginSuccess) {
          onLoginSuccess();
        }
      } else {
        setError('Login failed: No token received.');
      }
    } catch (err) {
      console.error("Login error:", err);
      if (err.response) {
        // Handle specific API errors (e.g., 401 Unauthorized)
        if (err.response.status === 401) {
          setError('Login failed: Incorrect email or password.');
        } else {
          setError(`Login failed: ${err.response.data.detail || 'Server error'}`);
        }
      } else if (err.request) {
        // Network error (request made but no response)
        setError('Login failed: Could not connect to the server.');
      } else {
        // Other errors (e.g., setup issue)
        setError('Login failed: An unexpected error occurred.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <h2>Login to Zoltar</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={loading}
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Password:</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
          />
        </div>
        {error && <p className="error-message">{error}</p>}
        <button type="submit" disabled={loading}>
          {loading ? 'Logging in...' : 'Login'}
        </button>
      </form>
    </div>
  );
}

export default Login; 