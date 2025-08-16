import React, { createContext, useState, useEffect, useContext } from 'react';
import { useParams } from 'react-router-dom';

const ServerStatusContext = createContext();

export const useServerStatus = () => useContext(ServerStatusContext);

export const ServerStatusProvider = ({ children }) => {
  const [isServerReady, setIsServerReady] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Connecting to server...');
  const [currentGameweek, setCurrentGameweek] = useState(null);
  const { teamId: teamIdFromUrl } = useParams();
  const [teamId, setTeamId] = useState(teamIdFromUrl);
  
  useEffect(() => {
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://fpl-chatbot-4zm5.onrender.com/api'; 

    const checkStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/status`);
        if (!response.ok) throw new Error('Server not responding.');
        
        const data = await response.json();
        if (data.status === 'ok') {
          setIsServerReady(true);
          setCurrentGameweek(data.current_gameweek);
          setStatusMessage(`Server ready. Current Gameweek: ${data.current_gameweek}`);
          return true; // Stop polling
        }
        setStatusMessage('Server is starting up, loading data...');
        return false; // Continue polling
      } catch (err) {
        setStatusMessage('Could not connect to the server. It might be starting up.');
        return false;
      }
    };

    const pollServer = async () => {
        if (await checkStatus()) return;
        const intervalId = setInterval(async () => {
            if (await checkStatus()) {
                clearInterval(intervalId);
            }
        }, 5000); // Poll every 5 seconds
        return () => clearInterval(intervalId);
    };

    pollServer();
  }, [teamId]);

  useEffect(() => {
    setTeamId(teamIdFromUrl);
  }, [teamIdFromUrl]);

  const value = { 
    isServerReady, 
    statusMessage, 
    currentGameweek, 
    teamId 
  };

  return (
    <ServerStatusContext.Provider value={value}>
      {children}
    </ServerStatusContext.Provider>
  );
};