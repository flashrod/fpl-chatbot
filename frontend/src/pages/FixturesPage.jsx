import React, { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';
import { useServerStatus } from '../contexts/ServerStatusContext';

const FixturesPage = () => {
  const { isServerReady, statusMessage } = useServerStatus();
  const [fixturesData, setFixturesData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchFixtures = async () => {
      if (!isServerReady) {
        setLoading(true);
        return;
      }
      
      setLoading(true);
      setError('');
      try {
        const response = await fetch('https://fpl-chatbot-4zm5.onrender.com/api/fixture-difficulty');
        if (!response.ok) {
          throw new Error(`Failed to fetch fixture data (Status: ${response.status})`);
        }
        const data = await response.json();
        setFixturesData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchFixtures();
  }, [isServerReady]);

  const getDifficultyColor = (difficulty) => {
    if (difficulty <= 2) return 'bg-teal-600 hover:bg-teal-500';
    if (difficulty === 3) return 'bg-slate-500 hover:bg-slate-400';
    if (difficulty === 4) return 'bg-rose-600 hover:bg-rose-500';
    if (difficulty >= 5) return 'bg-red-800 hover:bg-red-700';
    return 'bg-gray-400';
  };

  return (
    <div className="p-4 md:p-8 bg-slate-900 min-h-screen text-white overflow-y-auto font-sans">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2 text-emerald-400">Fixture Difficulty</h1>
        <p className="text-slate-400 mb-8">
          Teams are ranked by their average fixture difficulty over the next 5 gameweeks.
        </p>
        
        {loading && (
          <div className="flex justify-center items-center h-64 text-center">
            <div>
              <Loader2 className="w-12 h-12 animate-spin text-emerald-400 mx-auto" />
              <p className="mt-4 text-slate-400">{statusMessage}</p>
            </div>
          </div>
        )}

        {error && <div className="text-red-400 text-center p-4 bg-red-900/50 rounded-lg">{error}</div>}

        {!loading && !error && (
          <div className="space-y-3">
            {fixturesData.map((team) => (
              <div key={team.name} className="bg-slate-800/70 p-4 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between transition-all hover:bg-slate-800 border border-slate-700">
                <div className="flex items-center mb-4 sm:mb-0 sm:w-1/3">
                  <span className="font-bold text-lg w-40 truncate" title={team.name}>{team.name}</span>
                  <span className="text-xs font-mono bg-slate-700 text-slate-300 px-2 py-1 rounded-md">
                    Avg: {team.avg_difficulty}
                  </span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {team.fixture_details?.map((fixture, index) => (
                    <div 
                      key={index} 
                      className={`flex flex-col items-center justify-center p-2 rounded-md w-20 h-14 text-white text-center shadow-md transition-transform hover:scale-105 ${getDifficultyColor(fixture.difficulty)}`}
                      title={`Gameweek ${fixture.gameweek}`}
                    >
                      <span className="font-bold text-sm">{fixture.opponent}</span>
                      <span className="text-xs">({fixture.is_home ? 'H' : 'A'})</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default FixturesPage;
