import React, { useState, useEffect } from 'react';

// Keep same team colors
const teamColors = {
    'ARS': { bg: '#EF0107', text: '#FFFFFF', gradient: 'from-red-500 to-red-600' },
    'AVL': { bg: '#95BFE5', text: '#670E36', gradient: 'from-blue-300 to-purple-500' },
    // ... rest unchanged
};

const LoadingState = () => (
  <div className="min-h-screen bg-slate-900 flex items-center justify-center">
    <div className="text-center">
      <h2 className="text-4xl font-bold text-green-400 mb-4">FPL MANAGER</h2>
      <p className="text-lg text-gray-400 mb-4">Loading your team...</p>
      <div className="flex justify-center space-x-1">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="w-2 h-6 bg-green-500 rounded animate-pulse" style={{ animationDelay: `${i * 0.2}s` }}></div>
        ))}
      </div>
    </div>
  </div>
);

const EmptyState = () => (
  <div className="flex-grow bg-slate-800 flex flex-col justify-center items-center rounded-xl border border-gray-700 p-6">
    <div className="text-5xl mb-4">⚽</div>
    <h2 className="text-3xl font-bold text-white mb-2">Gameweek 1</h2>
    <p className="text-green-400 font-semibold mb-6">Starting Soon</p>
    <p className="text-gray-300 text-center max-w-lg">
      Your squad will be displayed once the game starts.
    </p>
  </div>
);

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
      try {
        const res = await fetch(`https://fpl-chatbot-4zm5.onrender.com/api/get-team-data/${teamId}`);
        if (!res.ok) throw new Error('Failed to fetch team data.');
        const data = await res.json();
        setTeamData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchTeamData();
  }, [teamId]);

  const renderPlayersByPosition = (position) =>
    teamData?.players
      ?.filter((p) => p.position === position)
      .map((p, i) => {
        const colors = teamColors[p.team_name] || { bg: '#ccc', text: '#000', gradient: 'from-gray-400 to-gray-500' };
        return (
          <div
            key={p.name}
            className="flex flex-col items-center text-center w-20"
          >
            {/* Jersey */}
            <svg viewBox="0 0 100 100" className="w-14 h-14">
              <defs>
                <linearGradient id={`grad-${p.team_name}-${i}`} x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor={colors.bg} />
                  <stop offset="100%" stopColor={colors.bg} stopOpacity="0.8" />
                </linearGradient>
              </defs>
              <path
                fill={`url(#grad-${p.team_name}-${i})`}
                stroke="#fff"
                strokeWidth="1"
                d="M30,20 L30,15 C30,10 32,8 35,8 L65,8 C68,8 70,10 70,15 L70,20 L75,25 L75,85 L25,85 L25,25 Z"
              />
            </svg>

            {/* Name */}
            <div className="text-xs font-semibold text-gray-100 truncate mt-1 w-full">
              {p.name}
            </div>
            <div
              className={`text-[10px] px-2 py-0.5 rounded-full mt-1 bg-gradient-to-r ${colors.gradient}`}
              style={{ color: colors.text }}
            >
              {p.team_name}
            </div>
          </div>
        );
      });

  if (loading) return <LoadingState />;
  if (error)
    return (
      <div className="min-h-screen flex justify-center items-center bg-slate-900 text-red-400">
        {error}
      </div>
    );

  const hasPlayers = teamData?.players?.length > 0;

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      <h1 className="text-5xl font-bold text-center text-green-400 mb-8">FPL MANAGER</h1>

      {!hasPlayers ? (
        <EmptyState />
      ) : (
        <div className="bg-slate-800 rounded-xl border border-gray-700 p-8">
          <div className="grid grid-rows-4 gap-y-6">
            <div className="flex justify-center">{renderPlayersByPosition('GKP')}</div>
            <div className="flex justify-center space-x-4">{renderPlayersByPosition('DEF')}</div>
            <div className="flex justify-center space-x-4">{renderPlayersByPosition('MID')}</div>
            <div className="flex justify-center space-x-4">{renderPlayersByPosition('FWD')}</div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TeamPitch;
