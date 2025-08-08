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
      const response = await fetch(`https://fpl-chatbot-4zm5.onrender.com/api/get-team-data/${inputId}`);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Team ID not found or invalid.');
      }
      onLogin(inputId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
        className="w-full max-w-md z-10 text-center"
    >
        <div className="mb-10">
            <h1 className="text-5xl md:text-7xl font-extrabold text-white tracking-tight mb-4">
              Get the <span className="bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent">Unfair Advantage</span>
            </h1>
            <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto">
              Stop guessing. Start winning. Our AI analyzes millions of data points to give you the ultimate edge.
            </p>
        </div>
        
        <div className="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-2xl shadow-2xl p-8">
            <form onSubmit={handleSubmit} className="w-full">
                <label htmlFor="team-id" className="block text-lg font-semibold text-white mb-3">Enter Your FPL Team ID</label>
                <div className="flex items-center space-x-3">
                    <input
                        type="text" 
                        inputMode="numeric"
                        pattern="[0-9]*"
                        id="team-id"
                        value={inputId}
                        onChange={(e) => setInputId(e.target.value)}
                        placeholder="e.g., 12345"
                        className="w-full px-4 py-3 bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-green-400 transition-all appearance-none"
                    />
                    <button 
                        type="submit" 
                        disabled={loading}
                        className="bg-gradient-to-r from-green-400 to-blue-500 text-slate-900 font-bold p-3 rounded-lg hover:opacity-90 transition-all transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center w-16 h-[52px]"
                    >
                        {loading ? <Loader2 className="w-6 h-6 animate-spin"/> : <ArrowRight className="w-6 h-6" />}
                    </button>
                </div>
            </form>

            {error && <p className="text-red-400 mt-4 text-sm">{error}</p>}

            <p className="text-xs text-slate-500 mt-6">
                Find your ID on the FPL website after clicking "My Team".
            </p>
        </div>
    </motion.div>
  );
};

export default LoginPage;
