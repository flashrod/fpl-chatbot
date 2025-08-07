import React from 'react';
import LoginPage from './LoginPage';
import LandingPageFeatures from '../components/LandingPageFeatures';
import LandingPageAbout from '../components/LandingPageAbout';
import { motion } from 'framer-motion';

const HomePage = ({ onLogin }) => {
  return (
    <div className="w-full h-screen overflow-y-auto bg-slate-900">
      {/* Animated background blobs */}
      <div className="absolute top-0 left-0 w-full h-full overflow-hidden z-0">
        <motion.div 
          className="absolute top-[-20%] left-[-20%] w-[40rem] h-[40rem] bg-green-500/10 rounded-full filter blur-3xl"
          animate={{ x: [0, 100, 0], y: [0, -50, 0] }}
          transition={{ repeat: Infinity, duration: 20, ease: "easeInOut" }}
        />
        <motion.div 
          className="absolute bottom-[-20%] right-[-20%] w-[50rem] h-[50rem] bg-blue-500/10 rounded-full filter blur-3xl"
          animate={{ x: [0, -80, 0], y: [0, 40, 0] }}
          transition={{ repeat: Infinity, duration: 22, ease: "easeInOut", delay: 2 }}
        />
      </div>
      
      {/* Hero Section with Login */}
      <div className="min-h-screen flex items-center justify-center relative">
        <LoginPage onLogin={onLogin} />
      </div>

      {/* Features Section */}
      <div className="relative">
        <LandingPageFeatures />
      </div>

      {/* About/Footer Section */}
      <div className="relative">
        <LandingPageAbout />
      </div>
    </div>
  );
};

export default HomePage;
