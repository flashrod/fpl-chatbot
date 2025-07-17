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
      const response = await fetch(`http://127.0.0.1:8000/api/get-team-data/${inputId}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Team ID not found. Please check and try again.');
      }
      onLogin(inputId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 text-white w-full h-full flex flex-col justify-center items-center p-6">
      <div className="text-center w-full max-w-sm">
        <h1 className="text-4xl font-bold mb-2">
          <span className="text-green-400">FPL</span> AI Assistant
        </h1>
        <p className="text-slate-400 mb-8">Get AI-powered insights for your team.</p>
        
        <form onSubmit={handleSubmit} className="w-full">
          <input
            type="text"
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            placeholder="Enter your FPL Team ID"
            className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-green-400"
            inputMode="numeric"
          />
          <button 
            type="submit" 
            disabled={loading}
            className="w-full mt-4 bg-green-500 text-slate-900 font-bold py-3 rounded-lg hover:bg-green-400 transition-colors disabled:bg-slate-600 disabled:cursor-not-allowed"
          >
            {loading ? 'Verifying...' : 'Continue'}
          </button>
        </form>

        {error && <p className="text-red-500 mt-4">{error}</p>}

        <div className="text-left mt-8 p-4 bg-slate-800/50 border border-slate-700 rounded-lg">
          <p className="text-sm text-slate-400">
            Find your ID in the URL on the FPL website:
            <br />
            <code className="text-green-400 text-xs break-all">
              fantasy.premierleague.com/entry/
              <span className="text-white font-bold bg-slate-700 px-1 rounded">YOUR_ID</span>
              /event/...
            </code>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
