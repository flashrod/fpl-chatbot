import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import TeamPitch from './pages/TeamPitch';
import MainLayout from './layouts/MainLayout';
import FixturesPage from './pages/FixturesPage';
import ChipsPage from './pages/ChipsPage'; // Import the new Chips page

function App() {
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);

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
