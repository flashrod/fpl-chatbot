import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Wand2, CalendarDays, ChevronsLeft, ChevronsRight, LogOut } from 'lucide-react';

const NavBar = ({ isCollapsed, setIsCollapsed, onLogout }) => {
  const location = useLocation();
  const isActive = (path) => location.pathname.startsWith(path);

  const navItems = [
    { path: "/team", icon: LayoutDashboard, label: "Dashboard" },
    { path: "/chat", icon: MessageSquare, label: "Chat" },
    { path: "/fixtures", icon: CalendarDays, label: "Fixtures" },
    { path: "/chips", icon: Wand2, label: "Chips" },
  ];

  return (
    <div className={`fixed top-0 left-0 h-full bg-slate-900 text-slate-300 transition-all duration-300 ease-in-out ${isCollapsed ? 'w-20' : 'w-64'}`}>
      <div className="flex flex-col h-full">
        {/* Header with Logo and Toggle Button */}
        <div className={`flex items-center h-20 border-b border-slate-800 ${isCollapsed ? 'justify-center' : 'justify-between px-4'}`}>
          <Link to="/team" className={`flex items-center space-x-2 ${isCollapsed ? 'hidden' : 'flex'}`}>
            <span className="text-3xl">⚽</span>
            <span className="font-bold text-xl text-white">
              <span className="text-green-400">FPL</span> AI
            </span>
          </Link>
          <button onClick={() => setIsCollapsed(!isCollapsed)} className="p-2 rounded-lg hover:bg-slate-800">
            {isCollapsed ? <ChevronsRight /> : <ChevronsLeft />}
          </button>
        </div>

        {/* Navigation Links */}
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
                  } ${isCollapsed ? 'justify-center' : ''}`}
                  title={item.label}
                >
                  <item.icon className="w-5 h-5" />
                  <span className={`${isCollapsed ? 'hidden' : 'block'}`}>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        {/* Logout Button */}
        <div className="px-4 py-6 border-t border-slate-800">
           <button
              onClick={onLogout}
              className={`flex items-center space-x-3 w-full px-4 py-3 rounded-lg transition-colors text-red-400 hover:bg-red-500/10 hover:text-red-300 ${isCollapsed ? 'justify-center' : ''}`}
              title="Logout"
            >
              <LogOut className="w-5 h-5" />
              <span className={`${isCollapsed ? 'hidden' : 'block'}`}>Logout</span>
            </button>
        </div>
      </div>
    </div>
  );
};

export default NavBar;
