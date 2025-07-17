import React from 'react';
import NavBar from '../components/NavBar';

const MainLayout = ({ children }) => {
  return (
    <div className="flex h-screen bg-slate-100">
      <NavBar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
};

export default MainLayout;
