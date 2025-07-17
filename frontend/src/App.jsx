import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import './App.css';

function App() {
  // We'll store the teamId in the App component to share it between pages.
  // We also check localStorage to see if it was saved from a previous session.
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);

  const handleLogin = (id) => {
    localStorage.setItem('fplTeamId', id); // Save to local storage for persistence
    setTeamId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem('fplTeamId');
    setTeamId(null);
  }

  return (
    <Router>
      <div className="app-container">
        <Routes>
          <Route 
            path="/login" 
            element={!teamId ? <LoginPage onLogin={handleLogin} /> : <Navigate to="/chat" />} 
          />
          <Route 
            path="/chat" 
            element={teamId ? <ChatPage teamId={teamId} onLogout={handleLogout} /> : <Navigate to="/login" />} 
          />
          <Route 
            path="*" 
            element={<Navigate to={teamId ? "/chat" : "/login"} />} 
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
