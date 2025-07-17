import React, { useState, useEffect } from 'react';

const TeamPitch = ({ teamId }) => {
  const [teamData, setTeamData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchTeamData = async () => {
      if (!teamId) {
        setError('No Team ID found. Please log in again.');
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const response = await fetch(`http://127.0.0.1:8000/api/get-team-data/${teamId}`);
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to fetch team data.');
        }
        const data = await response.json();
        setTeamData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchTeamData();
  }, [teamId]);

  const renderPlayersByPosition = (position) => {
    if (!teamData || !teamData.players) return null;
    return teamData.players
      .filter(player => player.position === position)
      .map(player => (
        <div key={player.name} className="flex flex-col items-center text-center w-20">
          <div className="w-10 h-10 mb-1">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" className="fill-current text-green-400">
              <path d="M78.5,30.83,76.24,7.5,50,15,23.76,7.5,21.5,30.83,50,45Z"/>
              <path d="M50,48,20,33V75a5,5,0,0,0,5,5H75V33Z" opacity="0.4"/>
            </svg>
          </div>
          <div className="bg-black/70 text-white text-xs font-bold px-2 py-0.5 rounded truncate w-full">{player.name}</div>
          <div className="text-xs text-slate-300">£{player.cost}m</div>
        </div>
      ));
  };

  if (loading) {
    return <div className="flex justify-center items-center h-full text-xl text-white bg-slate-800">Loading Team...</div>;
  }

  if (error) {
    return <div className="flex justify-center items-center h-full text-xl text-red-400 bg-slate-800">Error: {error}</div>;
  }

  return (
    <div className="p-4 md:p-8 bg-slate-800 h-full flex flex-col">
       <h1 className="text-3xl font-bold text-white mb-6">Team Dashboard</h1>
      <div className="flex-grow bg-gradient-to-b from-green-700 to-green-800 relative flex flex-col justify-center p-4 md:p-8 overflow-hidden border-4 border-white/10 rounded-xl">
        <div className="absolute inset-0 bg-no-repeat bg-center opacity-10" style={{backgroundImage: "radial-gradient(circle, white 80px, transparent 82px), repeating-linear-gradient(to bottom, transparent, transparent 19.5%, white 19.5%, white 20%)"}}></div>
        <div className="relative z-10 flex flex-col justify-around h-full space-y-4">
          <div className="flex justify-around items-center w-full">{renderPlayersByPosition('GKP')}</div>
          <div className="flex justify-around items-center w-full">{renderPlayersByPosition('DEF')}</div>
          <div className="flex justify-around items-center w-full">{renderPlayersByPosition('MID')}</div>
          <div className="flex justify-around items-center w-full">{renderPlayersByPosition('FWD')}</div>
        </div>
      </div>
    </div>
  );
};

export default TeamPitch;
