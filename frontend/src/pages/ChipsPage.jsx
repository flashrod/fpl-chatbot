import React, { useState, useEffect } from 'react';
import { Loader2, Zap, Shield, Star } from 'lucide-react';

const ChipsPage = () => {
  const [chipData, setChipData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchChipData = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await fetch('http://127.0.0.1:8000/api/chip-recommendations');
        if (!response.ok) {
          throw new Error('Failed to fetch chip recommendations.');
        }
        const data = await response.json();
        setChipData(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchChipData();
  }, []);

  const ChipCard = ({ title, recommendations, icon }) => (
    <div className="bg-slate-900/50 p-6 rounded-lg shadow-lg">
      <div className="flex items-center mb-4">
        {icon}
        <h2 className="text-2xl font-bold ml-3">{title}</h2>
      </div>
      <div className="space-y-4">
        {recommendations && recommendations.length > 0 ? (
          recommendations.map((rec, index) => (
            <div key={index} className="bg-slate-800 p-4 rounded-md border border-slate-700">
              <h3 className="font-bold text-green-400 text-lg">Gameweek {rec.gameweek}</h3>
              <p className="text-sm text-slate-400">
                Teams with multiple fixtures: <span className="font-bold text-white">{rec.teams_with_multiple_fixtures}</span>
              </p>
              <p className="text-sm text-slate-400">
                Average fixture difficulty: <span className="font-bold text-white">{rec.avg_fixture_difficulty}</span>
              </p>
            </div>
          ))
        ) : (
          <p className="text-slate-400">No standout gameweeks found for this chip based on current data.</p>
        )}
      </div>
    </div>
  );

  return (
    <div className="p-4 md:p-8 bg-slate-800 h-full text-white overflow-y-auto">
      <h1 className="text-3xl font-bold mb-6">AI Chip Strategy</h1>
      <p className="text-slate-400 mb-8">
        Our AI analyzes all upcoming fixtures to find the most opportune moments to use your powerful chips, focusing on Double Gameweeks and fixture swings.
      </p>
      
      {loading && (
        <div className="flex justify-center items-center h-64">
          <Loader2 className="w-12 h-12 animate-spin text-green-400" />
        </div>
      )}

      {error && <div className="text-red-400 text-center p-4 bg-red-900/50 rounded-lg">{error}</div>}

      {!loading && !error && chipData && (
        <div className="grid md:grid-cols-2 gap-8">
          <ChipCard 
            title="Bench Boost" 
            recommendations={chipData.bench_boost}
            icon={<Shield className="w-8 h-8 text-green-400" />}
          />
          <ChipCard 
            title="Triple Captain" 
            recommendations={chipData.triple_captain}
            icon={<Star className="w-8 h-8 text-green-400" />}
          />
        </div>
      )}
    </div>
  );
};

export default ChipsPage;
