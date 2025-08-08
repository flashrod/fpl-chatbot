import React, { useState } from 'react';
import NavBar from '../components/Navbar';

const MainLayout = ({ children, onLogout }) => {
  const [isNavCollapsed, setIsNavCollapsed] = useState(false);

  return (
    <div className="flex h-screen bg-slate-800">
      <NavBar 
        isCollapsed={isNavCollapsed} 
        setIsCollapsed={setIsNavCollapsed}
        onLogout={onLogout} 
      />
      <main className={`flex-1 transition-all duration-300 ease-in-out overflow-y-auto ${isNavCollapsed ? 'ml-20' : 'ml-64'}`}>
        {children}
      </main>
    </div>
  );
};

export default MainLayout;
