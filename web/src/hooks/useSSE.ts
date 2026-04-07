import { useState, useCallback, useRef } from 'react';

interface SSEResult {
  thinking: string;
  answer: string;
  result: any | null;
  isStreaming: boolean;
  isDoneThinking: boolean;
  stream: (query: string) => void;
}

export function useSSE(): SSEResult {
  const [thinking, setThinking] = useState('');
  const [answer, setAnswer] = useState('');
  const [result, setResult] = useState<any | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isDoneThinking, setIsDoneThinking] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const stream = useCallback((query: string) => {
    // Close any existing connection
    esRef.current?.close();

    setThinking('');
    setAnswer('');
    setResult(null);
    setIsStreaming(true);
    setIsDoneThinking(false);

    const es = new EventSource(`/api/ai/ask/stream?query=${encodeURIComponent(query)}`);
    esRef.current = es;

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);
      switch (data.type) {
        case 'thinking_start':
          break;
        case 'thinking':
          setThinking((prev) => prev + data.content);
          break;
        case 'thinking_end':
          setIsDoneThinking(true);
          break;
        case 'token':
          setAnswer((prev) => prev + data.content);
          break;
        case 'result':
          setResult(data.content);
          break;
        case 'done':
          es.close();
          setIsStreaming(false);
          break;
        case 'error':
          setAnswer(`Error: ${data.content}`);
          es.close();
          setIsStreaming(false);
          break;
      }
    };

    es.onerror = () => {
      es.close();
      setIsStreaming(false);
    };
  }, []);

  return { thinking, answer, result, isStreaming, isDoneThinking, stream };
}
