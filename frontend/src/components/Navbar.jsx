import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Wand2 } from 'lucide-react';

const NavBar = () => {
  const location = useLocation();
  const isActive = (path) => location.pathname === path;

  const navItems = [
    { path: "/team", icon: LayoutDashboard, label: "Dashboard" },
    { path: "/chat", icon: MessageSquare, label: "Chat" },
    { path: "/chips", icon: Wand2, label: "Chips" },
  ];

  return (
    <header className="flex flex-col w-64 bg-slate-900 text-slate-300">
      <div className="flex items-center justify-center h-20 border-b border-slate-800">
        <Link to="/team" className="flex items-center space-x-2">
          <span className="text-3xl">⚽</span>
          <span className="font-bold text-xl text-white">
            <span className="text-green-400">FPL</span> AI
          </span>
        </Link>
      </div>
      <nav className="flex-1 px-4 py-6">
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.path}>
              <Link
                to={item.path}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive(item.path)
                    ? 'bg-green-500/10 text-green-400 font-bold'
                    : 'hover:bg-slate-800 hover:text-white'
                }`}
              >
                <item.icon className="w-5 h-5" />
                <span>{item.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
};

export default NavBar;
