import React, { useEffect, useState } from "react";

function BrainFeed() {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState("DISCONNECTED");

  useEffect(() => {
    let ws;

    try {
      ws = new WebSocket("ws://localhost:8000/ws");
      setStatus("CONNECTING");

      ws.onopen = () => setStatus("CONNECTED");
      ws.onclose = () => setStatus("DISCONNECTED");
      ws.onerror = () => setStatus("ERROR");

      ws.onmessage = (event) => {
        setMessages((prev) => {
          const next = [event.data, ...prev];
          return next.slice(0, 20);
        });
      };
    } catch (e) {
      setStatus("ERROR");
    }

    return () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, []);

  return (
    <div className="brain-feed">
      <div className="brain-feed-header">
        <span>Brain Activity Feed</span>
        <span className={`feed-status feed-status-${status.toLowerCase()}`}>
          {status}
        </span>
      </div>
      <div className="brain-feed-body">
        {messages.length === 0 ? (
          <div className="feed-empty">
            Waiting for messages from backend…
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className="feed-line">
              {m}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default BrainFeed;
