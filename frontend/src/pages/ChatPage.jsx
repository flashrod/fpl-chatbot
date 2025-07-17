import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown'; // Import the markdown renderer
import remarkGfm from 'remark-gfm'; // Import the GFM plugin

const ChatPage = ({ teamId, onLogout }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setMessages([
      { sender: 'bot', text: `Hi! I'm ready to help with your FPL team (ID: ${teamId}). Ask me anything about your squad.`, error: false }
    ]);
  }, [teamId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { sender: 'user', text: input };
    setMessages(prev => [...prev, userMessage, { sender: 'bot', text: '', error: false }]);
    const currentInput = input;
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team_id: parseInt(teamId),
          question: currentInput,
        }),
      });

      if (!response.ok || !response.body) {
          throw new Error('Failed to get a valid response from the server.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let lastChunk = ''; // --- FIX: Keep track of the last chunk ---

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });

        // --- FIX: Check for and prevent duplicate chunks ---
        if (chunk !== lastChunk) {
            setMessages(prev => {
              const newMessages = [...prev];
              newMessages[newMessages.length - 1].text += chunk;
              return newMessages;
            });
            lastChunk = chunk;
        }
      }

    } catch (error) {
      console.error("Streaming Error:", error);
      setMessages(prev => {
         const newMessages = [...prev];
         const lastMessage = newMessages[newMessages.length - 1];
         if (lastMessage && lastMessage.sender === 'bot') {
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
      <header className="flex justify-between items-center p-4 bg-slate-900 text-white shadow-md">
        <h2 className="text-xl font-bold">FPL AI Chat</h2>
        <button onClick={onLogout} className="bg-slate-700 hover:bg-slate-600 text-white font-semibold py-2 px-4 rounded-lg transition-colors text-sm">
          Change Team
        </button>
      </header>

      <main className="flex-1 overflow-y-auto p-4 bg-slate-100">
        <div className="flex flex-col space-y-4" ref={messagesEndRef}>
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex items-end gap-2 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`prose prose-sm max-w-xs md:max-w-md lg:max-w-lg p-3 rounded-2xl transition-colors ${
                  msg.sender === 'user'
                    ? 'bg-green-500 text-black rounded-br-none'
                    : msg.error
                    ? 'bg-red-500 text-white rounded-bl-none'
                    : 'bg-slate-200 text-slate-800 rounded-bl-none'
                }`}
              >
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {msg.text}
                </ReactMarkdown>
                {isLoading && index === messages.length - 1 && <span className="animate-pulse">...</span>}
              </div>
            </div>
          ))}
        </div>
      </main>

      <footer className="p-4 bg-white border-t border-slate-200">
        <form onSubmit={handleSend} className="flex items-center space-x-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about transfers, players, etc..."
            className="flex-1 w-full px-4 py-2 bg-slate-100 border border-slate-300 rounded-full focus:outline-none focus:ring-2 focus:ring-green-500"
            disabled={isLoading}
          />
          <button 
            type="submit" 
            disabled={isLoading || !input.trim()}
            className="bg-green-500 hover:bg-green-600 text-black font-bold p-3 rounded-full transition-colors disabled:bg-slate-400 disabled:cursor-not-allowed"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6">
              <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
            </svg>
          </button>
        </form>
      </footer>
    </div>
  );
};

export default ChatPage;
