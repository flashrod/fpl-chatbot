import React from 'react';
import LoginPage from './LoginPage';
import LandingPageFeatures from '../components/LandingPageFeatures';
import LandingPageAbout from '../components/LandingPageAbout';
import { motion } from 'framer-motion';

const HomePage = ({ onLogin }) => {
  return (
    <div className="w-full h-screen overflow-y-auto bg-slate-900 text-white font-sans relative isolate">
      {/* Background Blobs */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <motion.div 
          className="absolute top-[-20%] left-[-20%] w-[40rem] h-[40rem] bg-green-500/10 rounded-full filter blur-3xl"
          animate={{ x: [0, 100, 0], y: [0, -50, 0] }}
          transition={{ repeat: Infinity, duration: 25, ease: "easeInOut" }}
        />
        <motion.div 
          className="absolute bottom-[-20%] right-[-20%] w-[50rem] h-[50rem] bg-blue-500/10 rounded-full filter blur-3xl"
          animate={{ x: [0, -80, 0], y: [0, 40, 0] }}
          transition={{ repeat: Infinity, duration: 28, ease: "easeInOut", delay: 2 }}
        />
      </div>
      
      {/* Main Content */}
      <div className="relative z-10">
        <div className="flex items-center justify-center min-h-screen px-4 py-20 md:py-32">
          <LoginPage onLogin={onLogin} />
        </div>
        <LandingPageFeatures />
        <LandingPageAbout />
      </div>
    </div>
  );
};

export default HomePage;
