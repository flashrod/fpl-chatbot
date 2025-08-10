import React, { createContext, useState, useEffect, useContext } from 'react';

const ServerStatusContext = createContext({
  isServerReady: false,
  statusMessage: 'Connecting to server...',
});

export const useServerStatus = () => useContext(ServerStatusContext);

export const ServerStatusProvider = ({ children }) => {
  const [isServerReady, setIsServerReady] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Connecting to server...');

  useEffect(() => {
    // Make sure this URL matches your deployed backend
    const API_BASE_URL = 'https://fpl-chatbot-4zm5.onrender.com'; 

    const checkStatus = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/status`);
        if (!response.ok) throw new Error('Server not responding.');
        
        const data = await response.json();
        if (data.players_in_master_df > 0) {
          console.log("Server is ready!");
          setIsServerReady(true);
          setStatusMessage('Server is ready.');
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
  }, []);

  return (
    <ServerStatusContext.Provider value={{ isServerReady, statusMessage }}>
      {children}
    </ServerStatusContext.Provider>
  );
};
