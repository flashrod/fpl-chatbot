import React from 'react';

const LandingPageAbout = () => {
  return (
    <footer className="bg-slate-900 text-slate-400 py-8 border-t border-slate-800">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <p className="text-lg font-semibold text-white mb-2">
          <span className="text-green-400">FPL</span> AI Assistant
        </p>
        <p className="text-sm">
          Built by FPL fans, for FPL fans. We combine the official FPL API with advanced stats to give you the edge.
        </p>
        <p className="text-xs mt-4">
          This is an independent project and is not affiliated with the Premier League or Fantasy Premier League.
        </p>
      </div>
    </footer>
  );
};

export default LandingPageAbout;
