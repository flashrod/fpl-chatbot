import React, { useState, useEffect } from 'react';

// Hardcoded team color map for reliability and better visuals
const teamColors = {
    'ARS': { bg: '#EF0107', text: '#FFFFFF' },
    'AVL': { bg: '#95BFE5', text: '#670E36' },
    'BOU': { bg: '#DA291C', text: '#000000' },
    'BRE': { bg: '#E30613', text: '#FFFFFF' },
    'BHA': { bg: '#0057B8', text: '#FFFFFF' },
    'CHE': { bg: '#034694', text: '#FFFFFF' },
    'CRY': { bg: '#1B458F', text: '#C4122E' },
    'EVE': { bg: '#003399', text: '#FFFFFF' },
    'FUL': { bg: '#FFFFFF', text: '#000000' },
    'LIV': { bg: '#C8102E', text: '#FFFFFF' },
    'LEI': { bg: '#003090', text: '#FDBE11' },
    'LEE': { bg: '#FFCD00', text: '#1D428A' },
    'LUT': { bg: '#F78F1E', text: '#000000' },
    'MCI': { bg: '#6CABDD', text: '#FFFFFF' },
    'MUN': { bg: '#DA291C', text: '#FFE500' },
    'NEW': { bg: '#241F20', text: '#FFFFFF' },
    'NFO': { bg: '#E53232', text: '#FFFFFF' },
    'NOR': { bg: '#00A650', text: '#FFF200' },
    'SHU': { bg: '#EE2737', text: '#FFFFFF' },
    'SOU': { bg: '#D71920', text: '#FFFFFF' },
    'TOT': { bg: '#FFFFFF', text: '#132257' },
    'WAT': { bg: '#FBEE23', text: '#ED2127' },
    'WHU': { bg: '#7A263A', text: '#1BB1E7' },
    'WOL': { bg: '#FDB913', text: '#231F20' },
    // Add any other teams as needed
    'BUR': { bg: '#6C1D45', text: '#99D6EA' },
    'IPS': { bg: '#1C3275', text: '#FFFFFF' },
};

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
      .map(player => {
        const colors = teamColors[player.team_name] || { bg: '#cccccc', text: '#000000' };
        return (
            <div key={player.name} className="flex flex-col items-center text-center w-20">
              <div className="w-12 h-12 mb-2 relative">
                <svg viewBox="0 0 100 100" className="w-full h-full">
                    {/* Jersey body */}
                    <path 
                        fill={colors.bg} 
                        d="M30,20 L30,15 C30,10 32,8 35,8 L65,8 C68,8 70,10 70,15 L70,20 L75,25 L75,85 L25,85 L25,25 Z"
                    />
                    
                    {/* Jersey collar */}
                    <path 
                        fill={colors.text} 
                        d="M35,8 L65,8 C68,8 70,10 70,15 L70,18 L50,22 L30,18 L30,15 C30,10 32,8 35,8 Z"
                    />
                    
                    {/* Jersey sleeves */}
                    <ellipse 
                        cx="25" cy="32" rx="5" ry="10" 
                        fill={colors.bg}
                    />
                    <ellipse 
                        cx="75" cy="32" rx="5" ry="10" 
                        fill={colors.bg}
                    />
                </svg>
              </div>
              <div className="bg-white/90 text-gray-800 text-xs font-medium px-2 py-1 rounded-full shadow-sm border border-gray-200 truncate w-full max-w-[80px]">
                {player.name}
              </div>
              <div 
                className="text-xs font-medium mt-1 px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: colors.bg,
                  color: colors.text
                }}
              >
                {player.team_name}
              </div>
            </div>
        );
    });
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full text-xl text-white bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="flex flex-col items-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-500 mb-4"></div>
          <span>Loading Team...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-full text-xl text-red-400 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
        <div className="text-center">
          <div className="text-6xl mb-4">⚠️</div>
          <div>Error: {error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 h-full flex flex-col">
      <h1 className="text-4xl font-bold text-white mb-8 text-center bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent">
        Team Dashboard
      </h1>
      
      <div className="flex-grow bg-gradient-to-b from-green-400 to-green-500 relative flex flex-col justify-center p-8 md:p-12 overflow-hidden rounded-xl shadow-xl">
        
        {/* Football pitch pattern */}
        <div className="absolute inset-0 opacity-25">
          {/* Center circle */}
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-32 h-32 border border-white rounded-full"></div>
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-1 h-1 bg-white rounded-full"></div>
          
          {/* Goal posts */}
          <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-16 h-4 border-2 border-white border-t-0 rounded-b-md">
            <div className="absolute -top-2 left-1/2 transform -translate-x-1/2 w-14 h-2 bg-white rounded-t-sm"></div>
          </div>
          <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 w-16 h-4 border-2 border-white border-b-0 rounded-t-md">
            <div className="absolute -bottom-2 left-1/2 transform -translate-x-1/2 w-14 h-2 bg-white rounded-b-sm"></div>
          </div>
          
          {/* Penalty areas */}
          <div className="absolute top-4 left-1/2 transform -translate-x-1/2 w-24 h-12 border border-white border-b-0 rounded-t-sm"></div>
          <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 w-24 h-12 border border-white border-t-0 rounded-b-sm"></div>
          
          {/* Goal areas */}
          <div className="absolute top-4 left-1/2 transform -translate-x-1/2 w-12 h-6 border border-white border-b-0 rounded-t-sm"></div>
          <div className="absolute bottom-4 left-1/2 transform -translate-x-1/2 w-12 h-6 border border-white border-t-0 rounded-b-sm"></div>
          
          {/* Halfway line */}
          <div className="absolute top-1/2 left-0 right-0 h-px bg-white transform -translate-y-1/2"></div>
          
          {/* Corner arcs */}
          <div className="absolute top-0 left-0 w-6 h-6 border border-white border-t-0 border-l-0 rounded-br-full"></div>
          <div className="absolute top-0 right-0 w-6 h-6 border border-white border-t-0 border-r-0 rounded-bl-full"></div>
          <div className="absolute bottom-0 left-0 w-6 h-6 border border-white border-b-0 border-l-0 rounded-tr-full"></div>
          <div className="absolute bottom-0 right-0 w-6 h-6 border border-white border-b-0 border-r-0 rounded-tl-full"></div>
        </div>
        
        <div className="relative z-10 grid grid-cols-5 grid-rows-4 gap-y-8 h-full">
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