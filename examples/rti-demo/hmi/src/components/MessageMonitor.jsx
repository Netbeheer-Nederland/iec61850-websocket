import React, { useState, useEffect, useCallback, useRef } from 'react';
import { executeApiCall, buildTargetValue } from '../services/apiService';

/**
 * MessageMonitor component for monitoring WebSocket messages from endpoints
 * 
 * @param {Object} props - Component props
 * @param {Object[]} props.endpoints - Array of endpoint objects with host, port, name, type
 * @param {string} props.title - Title for the monitor block (default: "WebSocket Messages")
 * @param {number} props.defaultInterval - Default polling interval in ms (default: 10000)
 * @param {boolean} props.showEndpointSelect - Whether to show endpoint selector (default: true)
 */
function MessageMonitor({ 
  endpoints = [], 
  title = 'WebSocket Messages',
  defaultInterval = 10000,
  showEndpointSelect = true
}) {
  const [selectedEndpoint, setSelectedEndpoint] = useState(null);
  const [interval, setInterval] = useState(defaultInterval);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [messages, setMessages] = useState([]);
  const [expandedMessageId, setExpandedMessageId] = useState(null);
  const [status, setStatus] = useState('Monitoring stopped');
  
  const pollingRef = useRef(null);
  const messageIdsRef = useRef(new Set());
  const currentIntervalRef = useRef(defaultInterval);

  // Fetch messages through BFF execute endpoint
  const getMessagesApi = useCallback((targetValue) => {
    return executeApiCall('messages', targetValue, {});
  }, []);

  const fetchMessages = useCallback(async () => {
    if (!selectedEndpoint) return;
    
    try {
      const targetValue = buildTargetValue(selectedEndpoint.host, selectedEndpoint.port);
      const result = await getMessagesApi(targetValue);
      
      if (result?.ok && result.payload) {
        // Handle the messages response
        let msgs = result.payload;
        
        // Normalize the response - handle different possible structures
        if (msgs.messages) {
          msgs = msgs.messages;
        } else if (msgs.result?.messages) {
          msgs = msgs.result.messages;
        } else if (msgs.result?.payload?.messages) {
          msgs = msgs.result.payload.messages;
        }
        
        if (Array.isArray(msgs)) {
          // Filter out duplicates based on message id
          const uniqueMsgs = msgs.filter(msg => {
            const msgId = msg.id || msg.message || JSON.stringify(msg);
            if (messageIdsRef.current.has(msgId)) {
              return false; // Duplicate
            }
            messageIdsRef.current.add(msgId);
            return true;
          });
          
          if (uniqueMsgs.length > 0) {
            setMessages(prev => [...prev, ...uniqueMsgs]);
          }
        } else if (typeof msgs === 'object') {
          const msgId = msgs.id || msgs.message || JSON.stringify(msgs);
          if (!messageIdsRef.current.has(msgId)) {
            messageIdsRef.current.add(msgId);
            setMessages(prev => [...prev, msgs]);
          }
        }
        
        setStatus(`Monitoring ${selectedEndpoint.name || selectedEndpoint.host}:${selectedEndpoint.port} (${messageIdsRef.current.size} messages)`);
      }
    } catch (error) {
      console.error('Failed to fetch messages:', error);
      setStatus(`Error: ${error.message || 'Failed to fetch messages'}`);
    }
  }, [selectedEndpoint, getMessagesApi]);

  // Start monitoring
  const startMonitoring = useCallback(() => {
    if (!selectedEndpoint) {
      setStatus('Please select an endpoint first');
      return;
    }
    
    setIsMonitoring(true);
    setStatus(`Starting monitoring for ${selectedEndpoint.name || selectedEndpoint.host}...`);
    
    // Clear existing poll
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
    }
    
    // Fetch immediately
    fetchMessages();
    
    // Set up polling using the current interval from ref
    pollingRef.current = setInterval(fetchMessages, currentIntervalRef.current);
  }, [selectedEndpoint, fetchMessages]);

  // Stop monitoring
  const stopMonitoring = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setIsMonitoring(false);
    setStatus('Monitoring stopped');
  }, []);

  // Clear messages - both locally and on the server
  const clearMessages = useCallback(async () => {
    if (!selectedEndpoint) return;
    
    try {
      const targetValue = buildTargetValue(selectedEndpoint.host, selectedEndpoint.port);
      const result = await executeApiCall('clear-messages', targetValue, {});
      
      if (result?.ok) {
        setMessages([]);
        messageIdsRef.current.clear();
        setExpandedMessageId(null);
        setStatus('Messages cleared');
      } else {
        setStatus(`Error clearing messages: ${result?.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to clear messages:', error);
      setStatus(`Error: ${error.message || 'Failed to clear messages'}`);
    }
  }, [selectedEndpoint]);

  // Handle interval change
  const handleIntervalChange = useCallback((e) => {
    const newInterval = parseInt(e.target.value, 10);
    setInterval(newInterval);
    currentIntervalRef.current = newInterval;
    
    // If currently monitoring, restart with new interval from ref
    if (isMonitoring && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = setInterval(fetchMessages, currentIntervalRef.current);
    }
  }, [isMonitoring, fetchMessages]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // Auto-select first endpoint if available
  useEffect(() => {
    if (endpoints.length > 0 && !selectedEndpoint) {
      setSelectedEndpoint(endpoints[0]);
    }
  }, [endpoints, selectedEndpoint]);

  // Keep currentIntervalRef in sync with interval state
  useEffect(() => {
    currentIntervalRef.current = interval;
  }, [interval]);

  // Format message timestamp
  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    
    // Handle ISO strings
    if (typeof timestamp === 'string') {
      try {
        const date = new Date(timestamp);
        if (!isNaN(date.getTime())) {
          return date.toLocaleTimeString();
        }
      } catch (e) {
        // Fall through
      }
    }
    
    // Handle numeric timestamps
    if (typeof timestamp === 'number') {
      return new Date(timestamp).toLocaleTimeString();
    }
    
    return String(timestamp);
  };

  // Get color for message direction
  const getDirectionColor = (direction) => {
    if (!direction) return 'var(--text-secondary)';
    const dir = direction.toLowerCase();
    if (dir === 'send' || dir === 'out' || dir === 'request') {
      return 'var(--success-color)';
    }
    if (dir === 'receive' || dir === 'in' || dir === 'response') {
      return 'var(--primary-color)';
    }
    return 'var(--text-secondary)';
  };

  // Get color for message category
  const getCategoryColor = (category) => {
    if (!category) return 'var(--text-muted)';
    const cat = category.toLowerCase();
    const categoryColors = {
      'read': 'var(--info-color)',
      'write': 'var(--warning-color)',
      'control': 'var(--danger-color)',
      'report': 'var(--primary-color)',
      'data': 'var(--success-color)',
    };
    return categoryColors[cat] || 'var(--text-muted)';
  };

  // Toggle message expansion
  const toggleMessage = useCallback((messageId) => {
    setExpandedMessageId(prev => prev === messageId ? null : messageId);
  }, []);

  // Syntax highlight JSON content with proper token detection
  const syntaxHighlightJson = (jsonString) => {
    try {
      const jsonObj = JSON.parse(jsonString);
      return (
        <pre 
          style={{
            margin: 0, 
            fontSize: '11px', 
            fontFamily: 'Consolas, "Courier New", monospace',
            whiteSpace: 'pre-wrap',
            wordWrap: 'break-word',
            maxWidth: '100%',
            overflowX: 'auto'
          }}
        >
          {jsonString.split('\n').map((line, i) => {
            const indent = line.match(/^\s*/)?.[0] || '';
            const trimmedLine = line.trim();
            const content = line.substring(indent.length);
            
            // Don't apply color to empty lines
            if (!trimmedLine) {
              return <span key={i}><span style={{ color: 'var(--text-muted)' }}>{indent}</span></span>;
            }
            
            let color = 'var(--text-primary)';
            
            // JSON structure tokens
            if (trimmedLine === '{' || trimmedLine === '}' || trimmedLine === '[' || trimmedLine === ']') {
              color = 'var(--text-secondary)';
            }
            // Booleans
            else if (trimmedLine === 'true' || trimmedLine === 'false') {
              color = 'var(--primary-color)';
            }
            // Null
            else if (trimmedLine === 'null') {
              color = 'var(--text-muted)';
            }
            // Numbers
            else if (!isNaN(trimmedLine) && !trimmedLine.includes('"')) {
              color = 'var(--warning-color)';
            }
            // Strings - check if it's a JSON string value
            else if (trimmedLine.startsWith('"') && trimmedLine.endsWith('"')) {
              // If it contains a colon, it's a key (before the colon)
              if (content.includes(':')) {
                // This is a key-value pair, extract the key part
                const keyPart = content.split(':')[0];
                const valuePart = content.split(':').slice(1).join(':');
                return (
                  <span key={i}>
                    <span style={{ color: 'var(--text-muted)' }}>{indent}</span>
                    <span style={{ color: 'var(--info-color)', fontWeight: '500' }}>{keyPart}:</span>
                    <span style={{ color: 'var(--success-color)' }}>{valuePart}</span>
                  </span>
                );
              }
              // Plain string value
              color = 'var(--success-color)';
            }
            // Keys without quotes (sometimes happens in malformed JSON display)
            else if (content.includes(':') && !content.includes('"')) {
              const keyPart = content.split(':')[0];
              const valuePart = content.split(':').slice(1).join(':');
              return (
                <span key={i}>
                  <span style={{ color: 'var(--text-muted)' }}>{indent}</span>
                  <span style={{ color: 'var(--info-color)', fontWeight: '500' }}>{keyPart}:</span>
                  <span style={{ color: 'var(--text-primary)' }}>{valuePart}</span>
                </span>
              );
            }
            
            return (
              <span key={i}>
                <span style={{ color: 'var(--text-muted)' }}>{indent}</span>
                <span style={{ color }}>{content}</span>
              </span>
            );
          })}
        </pre>
      );
    } catch (e) {
      return <pre style={{ margin: 0, fontSize: '11px' }}>{jsonString}</pre>;
    }
  };

  // Copy to clipboard helper
  const copyToClipboard = useCallback((text) => {
    try {
      navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      const result = document.execCommand('copy');
      document.body.removeChild(textArea);
      return result;
    }
  }, []);

  // Format message for display
  const formatMessageContent = (msg) => {
    if (!msg) return null;
    
    try {
      let jsonContent = null;
      let displayText = '';
      
      // Handle message.message field
      if (msg.message) {
        displayText = typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message, null, 2);
        jsonContent = displayText;
      }
      // Handle payload
      else if (msg.payload) {
        displayText = JSON.stringify(msg.payload, null, 2);
        jsonContent = displayText;
      }
      // Handle string
      else if (typeof msg === 'string') {
        try {
          // Try to parse as JSON
          JSON.parse(msg);
          displayText = msg;
          jsonContent = msg;
        } catch (e) {
          return <span>{msg}</span>;
        }
      }
      // Default: stringify the whole object
      else {
        displayText = JSON.stringify(msg, null, 2);
        jsonContent = displayText;
      }
      
      if (jsonContent) {
        return (
          <div style={{ position: 'relative' }}>
            {syntaxHighlightJson(jsonContent)}
            <button
              className="btn-icon"
              onClick={(e) => {
                e.stopPropagation();
                copyToClipboard(jsonContent);
              }}
              title="Copy to clipboard"
              style={{
                position: 'absolute',
                top: '4px',
                right: '4px',
                padding: '4px',
                fontSize: '10px',
                background: 'var(--bg-hover)',
                border: 'none'
              }}
            >
              <i className="fas fa-copy" style={{ fontSize: '10px' }}></i>
            </button>
          </div>
        );
      }
      
      return <span>{displayText}</span>;
    } catch (e) {
      return <span>Error displaying message</span>;
    }
  };

  return (
    <div className="monitor-block">
      <div className="monitor-header">
        <h3>{title}</h3>
        <div className="monitor-controls">
          {showEndpointSelect && endpoints.length > 0 && (
            <select 
              className="monitor-endpoint-select"
              value={selectedEndpoint ? buildTargetValue(selectedEndpoint.host, selectedEndpoint.port) : ''}
              onChange={(e) => {
                const target = e.target.value;
                if (target) {
                  const [host, port] = target.split(':');
                  const endpoint = endpoints.find(ep => ep.host === host && ep.port === parseInt(port, 10));
                  if (endpoint) {
                    setSelectedEndpoint(endpoint);
                  }
                }
              }}
            >
              {endpoints.length === 0 && (
                <option value="">No endpoints available</option>
              )}
              {endpoints.length > 0 && (
                <option value="">Select endpoint...</option>
              )}
              {endpoints.map((ep) => (
                <option 
                  key={buildTargetValue(ep.host, ep.port)}
                  value={buildTargetValue(ep.host, ep.port)}
                >
                  {ep.name || `${ep.host}:${ep.port}`}
                </option>
              ))}
            </select>
          )}
          {showEndpointSelect && endpoints.length === 0 && (
            <select className="monitor-endpoint-select" disabled>
              <option value="">No endpoints available</option>
            </select>
          )}
          
          <select 
            className="monitor-interval-select"
            value={interval}
            onChange={handleIntervalChange}
            disabled={!selectedEndpoint}
          >
            <option value="1000">1s</option>
            <option value="5000">5s</option>
            <option value="10000">10s</option>
            <option value="30000">30s</option>
          </select>
          
          <button 
            className="btn-icon monitor-control-btn" 
            title="Start Monitoring"
            onClick={startMonitoring}
            disabled={!selectedEndpoint || isMonitoring}
          >
            <i className="fas fa-play"></i>
          </button>
          
          <button 
            className="btn-icon monitor-control-btn" 
            title="Stop Monitoring"
            onClick={stopMonitoring}
            disabled={!isMonitoring}
          >
            <i className="fas fa-stop"></i>
          </button>
          
          <button 
            className="btn-icon monitor-control-btn" 
            title="Clear Messages"
            onClick={clearMessages}
            disabled={messages.length === 0}
          >
            <i className="fas fa-trash"></i>
          </button>
        </div>
      </div>
      
      <div className="monitor-status">
        {status}
      </div>
      
      <div className="monitor-messages">
        {messages.length === 0 ? (
          <p className="monitor-no-messages">
            No messages. {selectedEndpoint ? 'Start monitoring' : 'Select an endpoint and start monitoring'} to see WebSocket traffic.
          </p>
        ) : (
          <div className="message-list" style={{ maxHeight: '400px', overflowY: 'auto' }}>
            {messages.map((msg) => {
              const msgId = msg.id || msg.message || JSON.stringify(msg);
              const isExpanded = expandedMessageId === msgId;
              const directionColor = getDirectionColor(msg.direction);
              const categoryColor = getCategoryColor(msg.category);
              
              return (
                <div 
                  key={msgId}
                  className="message-card"
                  style={{
                    border: '1px solid var(--border-color)',
                    borderRadius: '6px',
                    marginBottom: '8px',
                    background: 'var(--bg-card)',
                    overflow: 'hidden'
                  }}
                >
                  <div 
                    className="message-header"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      cursor: 'pointer',
                      background: 'var(--bg-hover)',
                      borderBottom: '1px solid var(--border-color)'
                    }}
                    onClick={() => toggleMessage(msgId)}
                  >
                    <div className="message-meta" style={{ display: 'flex', gap: '12px', alignItems: 'center', fontSize: '11px' }}>
                      {msg.id && <span className="message-id" style={{ color: 'var(--text-muted)' }}>#{msg.id}</span>}
                      {msg.timestamp && <span className="message-timestamp" style={{ color: 'var(--text-muted)' }}>{formatTimestamp(msg.timestamp)}</span>}
                      {msg.direction && <span className="message-direction" style={{ color: directionColor, fontWeight: '600' }}>{msg.direction}</span>}
                      {msg.category && <span className="message-category" style={{ color: categoryColor }}>{msg.category}</span>}
                      {msg.service_type && <span className="message-service" style={{ color: 'var(--text-secondary)' }}>{msg.service_type}</span>}
                    </div>
                    <i 
                      className={`fas ${isExpanded ? 'fa-chevron-up' : 'fa-chevron-down'} message-toggle-icon`}
                      style={{ color: 'var(--text-muted)', fontSize: '12px' }}
                    ></i>
                  </div>
                  <div 
                    className="message-body"
                    style={{
                      padding: '12px',
                      display: isExpanded ? 'block' : 'none',
                      background: 'var(--bg-card)',
                      fontSize: '11px'
                    }}
                  >
                    {formatMessageContent(msg)}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export default MessageMonitor;
