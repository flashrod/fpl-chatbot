import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Loader2 } from 'lucide-react';
import { useServerStatus } from '../contexts/ServerStatusContext';

const ChatPage = () => {
  const { isServerReady, statusMessage, teamId } = useServerStatus();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (teamId) {
      setMessages([
        { role: 'assistant', text: `Hi! I'm ready to help with your FPL team (ID: ${teamId}). Ask me anything about players, transfers, or value.`, error: false }
      ]);
    }
  }, [teamId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !isServerReady) return;

    const userMessage = { role: 'user', text: input };
    const currentInput = input;
    setMessages(prev => [...prev, userMessage, { role: 'assistant', text: '', error: false }]);
    setInput('');
    setIsLoading(true);

    try {
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://fpl-chatbot-4zm5.onrender.com/api';
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: currentInput,
          // Reverted: Does not send team_id as it's not in the ChatRequest model for this version
          history: messages.map(m => ({ role: m.role, text: m.text })),
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error('Failed to get a valid response from the server.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let botResponse = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        botResponse += decoder.decode(value, { stream: true });
        
        setMessages(prev => {
          const newMessages = [...prev];
          const lastMessage = newMessages[newMessages.length - 1];
          if (lastMessage && lastMessage.role === 'assistant') {
            lastMessage.text = botResponse;
          }
          return newMessages;
        });
      }

    } catch (error) {
      console.error("Streaming Error:", error);
      setMessages(prev => {
         const newMessages = [...prev];
         const lastMessage = newMessages[newMessages.length - 1];
         if (lastMessage && lastMessage.role === 'assistant') {
            lastMessage.text = 'Sorry, I had a problem thinking. Please try again.';
            lastMessage.error = true;
         }
         return newMessages;
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-white w-full h-full flex flex-col">
      <main className="flex-1 overflow-y-auto p-4 bg-slate-100">
        <div className="flex flex-col space-y-4">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex items-end gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`prose prose-sm max-w-xs md:max-w-md lg:max-w-lg p-3 rounded-2xl transition-colors ${
                  msg.role === 'user'
                    ? 'bg-green-500 text-black rounded-br-none'
                    : msg.error
                    ? 'bg-red-500 text-white rounded-bl-none'
                    : 'bg-slate-200 text-slate-800 rounded-bl-none'
                }`}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.text}
                </ReactMarkdown>
                {isLoading && msg.role === 'assistant' && index === messages.length - 1 && <span className="animate-pulse">▍</span>}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </main>

      <footer className="p-4 bg-white border-t border-slate-200">
        {!isServerReady && (
          <div className="text-center text-xs text-slate-500 pb-2 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            {statusMessage}
          </div>
        )}
        <form onSubmit={handleSend} className="flex items-center space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={isServerReady ? "Ask about transfers, players, etc..." : "Please wait for server to connect..."}
            className="flex-1 w-full px-4 py-2 bg-slate-100 border border-slate-300 rounded-full focus:outline-none focus:ring-2 focus:ring-green-500"
            disabled={isLoading || !isServerReady}
          />
          <button 
            type="submit" 
            disabled={isLoading || !input.trim() || !isServerReady}
            className="bg-green-500 hover:bg-green-600 text-black font-bold p-3 rounded-full transition-colors disabled:bg-slate-400 disabled:cursor-not-allowed flex items-center justify-center w-12 h-12"
          >
            {isLoading ? <Loader2 className="w-6 h-6 animate-spin"/> : (
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
                <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
              </svg>
            )}
          </button>
        </form>
      </footer>
    </div>
  );
};

export default ChatPage;