import React from 'react';
import { BarChart, Bot, ShieldCheck, Trophy } from 'lucide-react';
import { motion } from 'framer-motion';

const features = [
  {
    icon: <Bot className="w-10 h-10 text-green-400" />,
    title: 'AI-Powered Chat',
    description: 'Get instant, data-driven advice on player transfers, captaincy choices, and team strategy from our intelligent FPL bot.',
  },
  {
    icon: <BarChart className="w-10 h-10 text-green-400" />,
    title: 'Fixture Analysis',
    description: 'Visualize team fixture difficulty over the next five gameweeks to plan your transfers and capitalize on easy runs.',
  },
  {
    icon: <ShieldCheck className="w-10 h-10 text-green-400" />,
    title: 'Strategic Chip Usage',
    description: 'Our AI analyzes double gameweeks and fixture swings to recommend the most opportune moments to use your precious chips.',
  },
  {
    icon: <Trophy className="w-10 h-10 text-green-400" />,
    title: 'Live League Tracking',
    description: 'Track your mini-league rivals in real-time during the gameweek to see how your players are performing.',
  },
];

const LandingPageFeatures = () => {
  return (
    <div className="py-12 md:py-20 bg-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center mb-12">
          <h2 className="text-3xl md:text-4xl font-extrabold">The Ultimate FPL Toolkit</h2>
          <p className="mt-4 text-lg text-slate-400">Everything you need to dominate your mini-leagues.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
          {features.map((feature, index) => (
            <motion.div 
              key={index} 
              className="glass-card p-6 text-center"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: index * 0.1 }}
              viewport={{ once: true }}
            >
              <div className="flex justify-center mb-4">
                {feature.icon}
              </div>
              <h3 className="text-xl font-bold mb-2">{feature.title}</h3>
              <p className="text-slate-400 text-sm">{feature.description}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default LandingPageFeatures;
