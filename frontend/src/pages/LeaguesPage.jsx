import React, { useState, useEffect } from 'react';
import { Loader2, ShieldCheck, Swords, Trophy, Users } from 'lucide-react';

const LeaguesPage = ({ teamId, gameweek }) => { // Pass teamId and gameweek as props
  const [liveData, setLiveData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchLiveData = async () => {
      if (!teamId || !gameweek) {
        setError('Team ID or Gameweek not provided.');
        setLoading(false);
        return;
      }
      setLoading(true);
      setError('');
      try {
        const response = await fetch(`https://fpl-chatbot-4zm5.onrender.com/api/live-gameweek-data/${teamId}/${gameweek}`);
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to fetch live data.');
        }
        const data = await response.json();
        setLiveData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchLiveData();
    // Refresh data every 60 seconds
    const interval = setInterval(fetchLiveData, 60000);
    return () => clearInterval(interval);
  }, [teamId, gameweek]);

  const PlayerRow = ({ player }) => (
    <tr className="border-b border-slate-700 hover:bg-slate-800/50">
      <td className="p-3">
        <div className="font-bold">{player.name}</div>
        <div className="text-xs text-slate-400">{player.team_name}</div>
      </td>
      <td className="p-3 text-center">{player.stats.minutes}</td>
      <td className="p-3 text-center">{player.live_points}</td>
      <td className="p-3 text-center">{player.stats.bonus}</td>
      <td className="p-3 text-center">{player.effective_ownership}%</td>
      <td className="p-3 text-center">
        {player.is_captain && <span className="font-bold text-amber-400">C</span>}
        {player.is_vice_captain && <span className="font-bold text-slate-400">V</span>}
      </td>
    </tr>
  );

  return (
    <div className="p-4 md:p-8 bg-slate-900 min-h-screen text-white font-sans">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-3xl font-bold text-emerald-400">Live Gameweek {gameweek}</h1>
            <p className="text-slate-400">Real-time points and stats for your team.</p>
          </div>
          {liveData && (
            <div className="text-right">
              <div className="text-4xl font-bold text-white">{liveData.total_points}</div>
              <div className="text-sm text-slate-400">Total Points</div>
            </div>
          )}
        </div>

        {loading && (
          <div className="flex justify-center items-center h-64">
            <Loader2 className="w-12 h-12 animate-spin text-emerald-400" />
            <span className="ml-4 text-lg">Fetching live data...</span>
          </div>
        )}

        {error && (
          <div className="text-red-400 text-center p-4 bg-red-900/50 rounded-lg">
            <h3 className="font-bold text-lg">Could not load live data</h3>
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && liveData && (
          <div className="bg-slate-800/70 rounded-lg shadow-lg overflow-hidden border border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-900/50">
                <tr>
                  <th className="p-3 text-left">Player</th>
                  <th className="p-3">Mins</th>
                  <th className="p-3">Pts</th>
                  <th className="p-3">Bonus</th>
                  <th className="p-3">EO (%)</th>
                  <th className="p-3"></th>
                </tr>
              </thead>
              <tbody>
                {liveData.players.map(player => (
                  <PlayerRow key={player.id} player={player} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default LeaguesPage;
