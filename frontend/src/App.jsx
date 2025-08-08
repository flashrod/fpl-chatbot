import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage'; // Import the new HomePage
import ChatPage from './pages/ChatPage';
import TeamPitch from './pages/TeamPitch';
import MainLayout from './layouts/MainLayout';
import FixturesPage from './pages/FixturesPage';
import ChipsPage from './pages/ChipsPage';
import LeaguesPage from './pages/LeaguesPage';

function App() {
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);
  const [currentGameweek, setCurrentGameweek] = useState(1);

  useEffect(() => {
    // In a full implementation, you would fetch the bootstrap data here
    // to get the actual current gameweek ID.
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
          {/* The root path now shows the HomePage if not logged in */}
          <Route 
            path="/" 
            element={!teamId ? <HomePage onLogin={handleLogin} /> : <Navigate to="/team" />} 
          />
          
          {/* Redirect /login to root for simplicity */}
          <Route 
            path="/login" 
            element={<Navigate to="/" />} 
          />

          {/* Protected routes are wrapped by MainLayout */}
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
                    {/* Any other path redirects to the main team dashboard */}
                    <Route path="*" element={<Navigate to="/team" />} />
                  </Routes>
                </MainLayout>
              ) : (
                <Navigate to="/" />
              )
            }
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
