import React, { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

const FixturesPage = () => {
  const [fixturesData, setFixturesData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchFixtures = async () => {
      setLoading(true);
      setError('');
      try {
        // Call the dedicated endpoint for fixture difficulty data.
        const response = await fetch('http://127.0.0.1:8000/api/fixture-difficulty');
        if (!response.ok) {
          throw new Error('Failed to fetch fixture data.');
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
  }, []);

  const getDifficultyColor = (difficulty) => {
    // --- UI/UX IMPROVEMENT ---
    // Create a 5-point color scale for more accurate visual representation.
    switch (difficulty) {
      case 1:
        return 'bg-emerald-500'; // Brightest green for easiest
      case 2:
        return 'bg-green-500';
      case 3:
        return 'bg-slate-500';   // Neutral grey
      case 4:
        return 'bg-red-500';
      case 5:
        return 'bg-red-700';     // Darkest red for hardest
      default:
        return 'bg-gray-400';
    }
  };

  return (
    <div className="p-4 md:p-8 bg-slate-800 h-full text-white overflow-y-auto">
      <h1 className="text-3xl font-bold mb-6">Upcoming Fixture Difficulty</h1>
      <p className="text-slate-400 mb-6">Teams are ranked by their average fixture difficulty over the next 5 gameweeks. Lower is better.</p>
      
      {loading && (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-12 h-12 animate-spin text-green-400" />
        </div>
      )}

      {error && <div className="text-red-400 text-center p-4 bg-red-900/50 rounded-lg">{error}</div>}

      {!loading && !error && (
        <div className="space-y-3">
          {fixturesData.map((team) => (
            <div key={team.short_name} className="bg-slate-900/50 p-4 rounded-lg flex flex-col sm:flex-row items-start sm:items-center justify-between transition-all hover:bg-slate-900">
              <div className="flex items-center mb-3 sm:mb-0">
                <span className="font-bold text-lg w-32 truncate">{team.name}</span>
                <span className="text-xs font-mono bg-slate-700 text-slate-300 px-2 py-1 rounded-md">
                  Avg: {team.avg_difficulty}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {team.fixture_details.map((fixture, index) => (
                  <div 
                    key={index} 
                    className={`flex flex-col items-center justify-center p-2 rounded-md w-24 h-12 text-white text-center shadow-md ${getDifficultyColor(fixture.difficulty)}`}
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
  );
};

export default FixturesPage;
