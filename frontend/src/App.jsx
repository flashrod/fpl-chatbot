import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import TeamPitch from './pages/TeamPitch';
import MainLayout from './layouts/MainLayout'; // Import the layout

// A placeholder for the chips page
const ChipsPage = () => <div className="p-8 text-white"><h1>Chip Recommendations</h1><p>This feature is coming soon!</p></div>;

function App() {
  const [teamId, setTeamId] = useState(localStorage.getItem('fplTeamId') || null);

  const handleLogin = (id) => {
    localStorage.setItem('fplTeamId', id);
    setTeamId(id);
  };

  // The logout function is no longer needed here as it's not passed down

  return (
    <Router>
      <div className="w-full h-screen bg-slate-900">
        <Routes>
          <Route 
            path="/login" 
            element={!teamId ? <LoginPage onLogin={handleLogin} /> : <Navigate to="/team" />} 
          />
          
          {/* Protected routes wrapped by MainLayout */}
          <Route 
            path="/team" 
            element={teamId ? <MainLayout><TeamPitch teamId={teamId} /></MainLayout> : <Navigate to="/login" />} 
          />
          <Route 
            path="/chat" 
            element={teamId ? <MainLayout><ChatPage teamId={teamId} /></MainLayout> : <Navigate to="/login" />} 
          />
           <Route 
            path="/chips" 
            element={teamId ? <MainLayout><ChipsPage /></MainLayout> : <Navigate to="/login" />} 
          />

          {/* Default route */}
          <Route 
            path="*" 
            element={<Navigate to={teamId ? "/team" : "/login"} />}
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
