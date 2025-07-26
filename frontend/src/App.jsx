import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import TeamPitch from './pages/TeamPitch';
import MainLayout from './layouts/MainLayout';
import FixturesPage from './pages/FixturesPage';
import ChipsPage from './pages/ChipsPage';
import LeaguesPage from './pages/LeaguesPage'; // Import the new Leagues page

function App() {
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);
  const [currentGameweek, setCurrentGameweek] = useState(1); // State for current gameweek

  // A real app might fetch this from the backend on load
  // For now, we'll assume the backend logic provides the current live gameweek
  // This is a placeholder for that future logic.
  useEffect(() => {
    // In a full implementation, you would fetch the bootstrap data here
    // to get the actual current gameweek ID.
    // For example:
    // fetch('http://127.0.0.1:8000/api/game-status')
    //   .then(res => res.json())
    //   .then(data => setCurrentGameweek(data.current_gameweek_id));
  }, []);


  const handleLogin = (id) => {
    localStorage.setItem('fplTeamId', id);
    setTeamId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem('fplTeamId');
    setTeamId(null);
  };

  return (
    <Router>
      <div className="w-full h-screen bg-slate-900">
        <Routes>
          <Route 
            path="/login" 
            element={!teamId ? <LoginPage onLogin={handleLogin} /> : <Navigate to="/team" />} 
          />
          
          {/* Protected routes are now wrapped by MainLayout */}
          <Route 
            path="/*"
            element={
              teamId ? (
                <MainLayout onLogout={handleLogout}>
                  <Routes>
                    <Route path="/team" element={<TeamPitch teamId={teamId} />} />
                    <Route path="/chat" element={<ChatPage teamId={teamId} />} />
                    <Route path="/fixtures" element={<FixturesPage />} />
                    <Route path="/chips" element={<ChipsPage />} />
                    <Route path="/leagues" element={<LeaguesPage teamId={teamId} gameweek={currentGameweek} />} />
                    <Route path="*" element={<Navigate to="/team" />} />
                  </Routes>
                </MainLayout>
              ) : (
                <Navigate to="/login" />
              )
            }
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
