import React, { useState } from 'react';
import { ArrowRight, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

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
      // API call to verify the team ID
      const response = await fetch(`http://127.0.0.1:8000/api/get-team-data/${inputId}`);
      if (!response.ok) {
        try {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Team ID not found. Please check the ID and try again.');
        } catch {
            throw new Error(`Error: ${response.status} ${response.statusText}`);
        }
      }
      onLogin(inputId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4 relative overflow-hidden bg-slate-900 text-white font-sans">
      
      {/* Animated Background Shapes using Framer Motion */}
      <motion.div 
        className="absolute top-[-10%] left-[-10%] w-72 h-72 bg-green-500/20 rounded-full filter blur-3xl"
        animate={{
          x: [0, 100, 20, 0],
          y: [0, -50, 30, 0],
          scale: [1, 1.2, 0.9, 1],
        }}
        transition={{
          repeat: Infinity,
          duration: 20,
          ease: "easeInOut",
        }}
      />
      <motion.div 
        className="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-500/20 rounded-full filter blur-3xl"
         animate={{
          x: [0, -80, -20, 0],
          y: [0, 40, -30, 0],
          scale: [1, 1.1, 0.8, 1],
        }}
        transition={{
          repeat: Infinity,
          duration: 18,
          ease: "easeInOut",
          delay: 2,
        }}
      />

      <div className="w-full max-w-md z-10 text-center">
          <div className="mb-10">
              <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight mb-3 bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent">
                FPL AI Assistant
              </h1>
              <p className="text-lg text-slate-400">
                  Your personal Fantasy Premier League genius.
              </p>
          </div>

          <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-2xl p-8 shadow-2xl">
              <form onSubmit={handleSubmit}>
                  <label htmlFor="team-id" className="block text-sm font-medium text-slate-300 mb-2">Enter Your FPL Team ID</label>
                  <div className="flex items-center space-x-3">
                      <input 
                          type="number" 
                          id="team-id" 
                          name="team-id"
                          placeholder="e.g., 12345"
                          className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-green-400 transition-all"
                          required
                          value={inputId}
                          onChange={(e) => setInputId(e.target.value)}
                          disabled={loading}
                      />
                      <button 
                          type="submit"
                          className="bg-green-500 text-slate-900 font-bold p-3 rounded-lg hover:bg-green-400 transition-colors transform hover:scale-105 flex items-center justify-center h-[50px] w-auto disabled:bg-slate-600 disabled:cursor-not-allowed"
                          disabled={loading}
                      >
                          {loading ? <Loader2 className="w-6 h-6 animate-spin" /> : <ArrowRight className="w-6 h-6" />}
                      </button>
                  </div>
              </form>
              {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
              <p className="text-xs text-slate-500 mt-4">
                  Find your ID on the FPL website after clicking "My Team".
              </p>
          </div>
      </div>
    </div>
  );
};

export default LoginPage;
