import React, { createContext, useState, useEffect, useContext } from 'react';
import { useParams } from 'react-router-dom';

const ServerStatusContext = createContext();

export const useServerStatus = () => useContext(ServerStatusContext);

export const ServerStatusProvider = ({ children }) => {
  const [isServerReady, setIsServerReady] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Connecting to server...');
  
  // MODIFIED: Added state for gameweek, team ID, and user's full team data
  const [currentGameweek, setCurrentGameweek] = useState(null);
  const { teamId: teamIdFromUrl } = useParams();
  const [teamId, setTeamId] = useState(teamIdFromUrl);
  const [userTeamData, setUserTeamData] = useState(null);

  // MODIFIED: New function to fetch team data via the proxy
  const fetchUserTeam = async (id, gw) => {
    if (!id || !gw) return;
    try {
      console.log(`Fetching team data for ID: ${id} Gameweek: ${gw}`);
      // This calls the proxy we created in the frontend folder
      const response = await fetch(`/api/fpl/entry/${id}/event/${gw}/picks/`);
      if (!response.ok) {
        throw new Error('Could not fetch user team data from proxy.');
      }
      const data = await response.json();
      setUserTeamData(data); // Store the data globally
      console.log('Successfully fetched and stored user team data.');
    } catch (error) {
      console.error(error);
    }
  };

  useEffect(() => {
    // MODIFIED: Using environment variable for a flexible API URL
    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://fpl-chatbot-4zm5.onrender.com/api'; 

    const checkStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/status`);
        if (!response.ok) throw new Error('Server not responding.');
        
        const data = await response.json();
        if (data.status === 'ok' && data.players_in_master_df > 0) {
          console.log("Server is ready!");
          setIsServerReady(true);
          setCurrentGameweek(data.current_gameweek); // MODIFIED: Store the current gameweek
          setStatusMessage(`Server ready. Current Gameweek: ${data.current_gameweek}`);
          
          // MODIFIED: Fetch user's team data as soon as the server is ready
          if (teamId) {
            fetchUserTeam(teamId, data.current_gameweek);
          }
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
  }, [teamId]); // MODIFIED: Re-run this logic if the teamId in the URL changes

  // This keeps the teamId state in sync if the user navigates between teams
  useEffect(() => {
    setTeamId(teamIdFromUrl);
  }, [teamIdFromUrl]);

  // MODIFIED: Expose all the new data to the rest of the app
  const value = { 
    isServerReady, 
    statusMessage, 
    currentGameweek, 
    teamId, 
    userTeamData 
  };

  return (
    <ServerStatusContext.Provider value={value}>
      {children}
    </ServerStatusContext.Provider>
  );
};