import React, { useState, useEffect, useRef } from 'react';
// We don't need axios anymore for this component
// import axios from 'axios'; 

const ChatPage = ({ teamId, onLogout }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setMessages([
      { sender: 'bot', text: `Hi! I'm ready to help with your FPL team (ID: ${teamId}). What's on your mind?` }
    ]);
  }, [teamId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = { sender: 'user', text: input };
    // Add the user's message and a placeholder for the bot's response
    setMessages(prev => [...prev, userMessage, { sender: 'bot', text: '' }]);
    setInput('');
    setIsLoading(true);

    try {
      // --- THE STREAMING LOGIC ---
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          team_id: parseInt(teamId),
          question: input,
        }),
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      // Read chunks from the stream
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        const chunk = decoder.decode(value);
        // Update the last message (the bot's response) with the new chunk
        setMessages(prev => {
          const lastMessage = prev[prev.length - 1];
          const updatedLastMessage = { ...lastMessage, text: lastMessage.text + chunk };
          return [...prev.slice(0, -1), updatedLastMessage];
        });
      }

    } catch (error) {
      console.error("Streaming Error:", error);
      setMessages(prev => {
        const lastMessage = prev[prev.length - 1];
        const updatedLastMessage = { ...lastMessage, text: 'Sorry, I had a problem thinking. Please try again.' };
        return [...prev.slice(0, -1), updatedLastMessage];
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-page">
      <div className="chat-header">
        <h2>FPL AI Chatbot</h2>
        <button onClick={onLogout} className="logout-button">Change Team ID</button>
      </div>
      <div className="chat-window">
        <div className="messages-list" ref={messagesEndRef}>
          {messages.map((msg, index) => (
            <div key={index} className={`message-bubble ${msg.sender}`}>
              <p>{msg.text}{isLoading && index === messages.length - 1 ? '...' : ''}</p>
            </div>
          ))}
        </div>
      </div>
      <form onSubmit={handleSend} className="chat-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about transfers, players, etc..."
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !input.trim()}>Send</button>
      </form>
    </div>
  );
};

export default ChatPage;
