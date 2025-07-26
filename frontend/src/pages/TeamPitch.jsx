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
    if (!teamData || !teamData.players || teamData.players.length === 0) {
        if (position === 'MID') {
            return <div className="text-slate-300/50 text-center col-span-full">Your team lineup will appear here once the season starts.</div>
        }
        return null;
    }
    
    return teamData.players
      .filter(player => player.position === position)
      .map(player => (
        <div key={player.name} className="flex flex-col items-center text-center w-20">
          <div className="w-12 h-12 mb-1">
            {/* Player Shirt SVG */}
            <svg viewBox="0 0 36 36" className="w-full h-full">
                <g>
                    {/* Main body of the shirt */}
                    <path 
                        fill={player.team_shirt_color} 
                        d="M13.7,13.7L13,4.9c0-0.3,0.2-0.5,0.5-0.5h9c0.3,0,0.5,0.2,0.5,0.5l-0.7,8.8L18,18L13.7,13.7z"
                    />
                    {/* Sleeves */}
                    <path 
                        fill={player.team_shirt_sleeve_color} 
                        d="M13.7,13.7L13,4.9c0-0.3-0.2-0.5-0.5-0.5h-2L4,7.8v10.4L13.7,13.7z"
                    />
                    <path 
                        fill={player.team_shirt_sleeve_color} 
                        d="M23,4.4c-0.3,0-0.5,0.2-0.5,0.5l0.7,8.8L32,22.2V7.8L25.5,4.4H23z"
                    />
                    {/* Main body lower part */}
                    <path
                        fill={player.team_shirt_color}
                        d="M13.7,13.7L4,22.2v8.3c0,0.3,0.2,0.5,0.5,0.5h27c0.3,0,0.5-0.2,0.5-0.5v-8.3L22.3,13.7L18,18L13.7,13.7z"
                    />
                </g>
            </svg>
          </div>
          <div className="bg-black/70 text-white text-xs font-bold px-2 py-0.5 rounded truncate w-full">{player.name}</div>
          <div className="text-xs text-slate-300">{player.team_name}</div>
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
        <div className="absolute inset-0 bg-no-repeat bg-center opacity-10" style={{backgroundImage: "radial-gradient(circle at center, white 80px, transparent 82px), repeating-linear-gradient(to bottom, transparent, transparent 19.5%, white 19.5%, white 20%)"}}></div>
        <div className="relative z-10 grid grid-cols-5 grid-rows-4 gap-y-4 h-full">
          <div className="col-span-5 flex justify-around items-center">{renderPlayersByPosition('GKP')}</div>
          <div className="col-span-5 flex justify-around items-center">{renderPlayersByPosition('DEF')}</div>
          <div className="col-span-5 flex justify-around items-center">{renderPlayersByPosition('MID')}</div>
          <div className="col-span-5 flex justify-around items-center">{renderPlayersByPosition('FWD')}</div>
        </div>
      </div>
    </div>
  );
};

export default TeamPitch;
