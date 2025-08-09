import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ChatPage from './pages/ChatPage';
import TeamPitch from './pages/TeamPitch';
import MainLayout from './layouts/MainLayout';
import FixturesPage from './pages/FixturesPage';
import ChipsPage from './pages/ChipsPage';
import LeaguesPage from './pages/LeaguesPage';
import { ServerStatusProvider } from './contexts/ServerStatusContext'; // <-- IMPORT

function App() {
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);
  const [currentGameweek, setCurrentGameweek] = useState(1);

  const handleLogin = (id) => {
    localStorage.setItem('fplTeamId', id);
    setTeamId(id);
  };

  const handleLogout = () => {
    localStorage.removeItem('fplTeamId');
    setTeamId(null);
  };

  return (
    // WRAP EVERYTHING IN THE PROVIDER
    <ServerStatusProvider>
      <Router>
        <div className="w-full h-screen bg-slate-900">
          <Routes>
            <Route 
              path="/" 
              element={!teamId ? <HomePage onLogin={handleLogin} /> : <Navigate to="/team" />} 
            />
            <Route path="/login" element={<Navigate to="/" />} />
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
                  <Navigate to="/" />
                )
              }
            />
          </Routes>
        </div>
      </Router>
    </ServerStatusProvider>
  );
}

export default App;
