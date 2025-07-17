import React, { useState } from 'react';

const LoginPage = ({ onLogin }) => {
  const [inputId, setInputId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!/^\d+$/.test(inputId)) {
      setError('Please enter a valid FPL Team ID (numbers only).');
      return;
    }
    
    setLoading(true);
    setError('');

    try {
      // We'll verify the team ID by trying to fetch its data.
      const response = await fetch(`http://127.0.0.1:8000/api/get-team-data/${inputId}`);
      if (!response.ok) {
        throw new Error('Team ID not found. Please check the ID and try again.');
      }
      // If the fetch is successful, we call the onLogin function from App.jsx
      onLogin(inputId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <h1>FPL AI Assistant</h1>
      <p>Enter your FPL Team ID to begin.</p>
      <form onSubmit={handleSubmit}>
        <input
          type="text"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          placeholder="Enter FPL Team ID"
          className="team-id-input"
          inputMode="numeric"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Verifying...' : 'Continue'}
        </button>
      </form>
      {error && <p className="error-message">{error}</p>}
      <div className="help-text">
        <p>You can find your ID in the URL of your team's page on the FPL website.</p>
        <p>e.g., `fantasy.premierleague.com/entry/YOUR_ID/event/...`</p>
      </div>
    </div>
  );
};

export default LoginPage;
