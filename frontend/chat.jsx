const {
  useState: useChatState,
  useEffect: useChatEffect,
  useRef: useChatRef,
  useCallback: useChatCallback,
} = React;

const CHAT_WELCOME_MESSAGE = "Ask me anything about this video. I'll note when an answer comes from general knowledge rather than the video.";
const DEMO_CHAT_WELCOME_MESSAGE = window.DEMO_CHAT_WELCOME_MESSAGE || "Ask me anything about this video.";
const DEMO_CHAT_REPLY = window.DEMO_CHAT_REPLY || "This is a demo video in the portfolio build.";
const chatStateCache = new Map();

function createDefaultChatState() {
  return {
    indexStatus: "idle",
    indexProgress: 0,
    indexError: null,
    messages: [{ role: "assistant", content: CHAT_WELCOME_MESSAGE }],
  };
}

function getChatStorageKey(videoId) {
  return `yt-distiller-ai-chat:${videoId}`;
}

function loadStoredChatState(videoId) {
  const defaults = createDefaultChatState();
  if (!videoId) return defaults;

  if (chatStateCache.has(videoId)) {
    return chatStateCache.get(videoId);
  }

  try {
    const raw = sessionStorage.getItem(getChatStorageKey(videoId));
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    const next = {
      indexStatus: typeof parsed.indexStatus === "string" ? parsed.indexStatus : defaults.indexStatus,
      indexProgress: Number(parsed.indexProgress) || 0,
      indexError: parsed.indexError || null,
      messages: Array.isArray(parsed.messages) && parsed.messages.length ? parsed.messages : defaults.messages,
    };
    chatStateCache.set(videoId, next);
    return next;
  } catch (e) {
    sessionStorage.removeItem(getChatStorageKey(videoId));
    return defaults;
  }
}

function persistChatState(videoId, nextState) {
  if (!videoId) return;
  chatStateCache.set(videoId, nextState);
  try {
    sessionStorage.setItem(getChatStorageKey(videoId), JSON.stringify(nextState));
  } catch (e) {
    // Ignore storage failures and keep the in-memory chat usable.
  }
}

function ChatMessage({ msg }) {
  const isUser = msg.role === "user";
  const isGenKnowledge = typeof msg.content === "string" && msg.content.startsWith("[General knowledge]");

  function renderContent(text) {
    if (!text) return null;
    const parts = text.split(/(\[\d{2}:\d{2}\])/g);
    return parts.map((part, i) => {
      const match = part.match(/^\[(\d{2}:\d{2})\]$/);
      if (match) {
        return (
          <span
            key={i}
            className="chat-timestamp-chip"
            title="Scrolls to approximately this point in the transcript"
            onClick={() => window.__scrollTranscriptTo && window.__scrollTranscriptTo(match[1])}
          >
            ~{match[1]}
          </span>
        );
      }
      return <span key={i}>{part}</span>;
    });
  }

  return (
    <div className={`chat-message chat-message--${isUser ? "user" : "assistant"} ${isGenKnowledge ? "chat-message--general" : ""}`}>
      <div className="chat-message__bubble">
        {isUser ? msg.content : renderContent(msg.content)}
      </div>
    </div>
  );
}

function ChatTab({ videoId, summaryDone }) {
  const isDemoVideo = videoId === "demo";
  const initialState = loadStoredChatState(videoId);
  const [indexStatus, setIndexStatus] = useChatState(initialState.indexStatus);
  const [indexProgress, setIndexProgress] = useChatState(initialState.indexProgress);
  const [indexError, setIndexError] = useChatState(initialState.indexError);
  const [messages, setMessages] = useChatState(initialState.messages);
  const [input, setInput] = useChatState("");
  const [sending, setSending] = useChatState(false);
  const pollRef = useChatRef(null);
  const bottomRef = useChatRef(null);
  const requestSeqRef = useChatRef(0);
  const activeRequestRef = useChatRef({ id: 0, videoId: null, controller: null });

  function cancelActiveRequest() {
    requestSeqRef.current += 1;
    if (activeRequestRef.current.controller) {
      activeRequestRef.current.controller.abort();
    }
    activeRequestRef.current = { id: requestSeqRef.current, videoId: null, controller: null };
  }

  useChatEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const startPolling = useChatCallback((vid) => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const response = await fetch(`/api/index/status?video_id=${vid}`);
        const data = await response.json();
        if (data.status === "ready") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setIndexStatus("ready");
        } else if (data.status === "failed") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setIndexStatus("failed");
          setIndexError(data.message || data.error || "Indexing failed");
        } else if (data.status === "indexing") {
          setIndexProgress(data.progress_pct || 0);
        }
      } catch (e) {
        // Keep polling through transient network issues.
      }
    }, 5000);
  }, []);

  useChatEffect(() => {
    return () => {
      cancelActiveRequest();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  useChatEffect(() => {
    cancelActiveRequest();
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    const next = loadStoredChatState(videoId);
    setIndexStatus(next.indexStatus);
    setIndexProgress(next.indexProgress);
    setIndexError(next.indexError);
    setMessages(next.messages);
    setInput("");
    setSending(false);
    if (videoId === "demo") {
      setIndexStatus("ready");
      setIndexProgress(100);
      setIndexError(null);
      setMessages((prev) => {
        if (Array.isArray(next.messages) && next.messages.length) {
          return next.messages;
        }
        return [{ role: "assistant", content: DEMO_CHAT_WELCOME_MESSAGE }];
      });
    }
  }, [videoId]);

  useChatEffect(() => {
    persistChatState(videoId, { indexStatus, indexProgress, indexError, messages });
  }, [videoId, indexStatus, indexProgress, indexError, messages]);

  function buddyHeaders() {
    const headers = { "Content-Type": "application/json" };
    const apiKey = sessionStorage.getItem("buddy_api_key");
    const provider = sessionStorage.getItem("buddy_provider");
    const model = sessionStorage.getItem("buddy_model");
    if (apiKey) headers["X-Buddy-Api-Key"] = apiKey;
    if (provider) headers["X-Buddy-Provider"] = provider;
    if (model) headers["X-Buddy-Model"] = model;
    return headers;
  }

  const triggerIndex = useChatCallback(async () => {
    if (!videoId || !summaryDone) return;
    setIndexStatus("indexing");
    setIndexError(null);
    try {
      const response = await fetch("/api/index", {
        method: "POST",
        headers: buddyHeaders(),
        body: JSON.stringify({ video_id: videoId }),
      });
      if (response.status === 200) {
        setIndexStatus("ready");
      } else if (response.status === 202) {
        startPolling(videoId);
      } else if (response.status === 503) {
        const data = await response.json();
        setIndexStatus("failed");
        setIndexError(data.message || "Indexing service unavailable. Please try again.");
      }
    } catch (e) {
      setIndexStatus("failed");
      setIndexError("Network error. Please try again.");
    }
  }, [videoId, summaryDone, startPolling]);

  useChatEffect(() => {
    if (isDemoVideo) return;
    if (indexStatus === "idle" && summaryDone && videoId) {
      triggerIndex();
    }
  }, [isDemoVideo, indexStatus, summaryDone, videoId, triggerIndex]);

  useChatEffect(() => {
    if (isDemoVideo) return;
    if (indexStatus === "indexing" && videoId) {
      startPolling(videoId);
    }
  }, [isDemoVideo, indexStatus, videoId, startPolling]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || sending) return;
    if (isDemoVideo) {
      setSending(true);
      setInput("");
      setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: DEMO_CHAT_REPLY }]);
      setSending(false);
      return;
    }

    const controller = new AbortController();
    const requestId = requestSeqRef.current + 1;
    requestSeqRef.current = requestId;
    activeRequestRef.current = { id: requestId, videoId, controller };

    setSending(true);
    setInput("");
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "", _streaming: true }]);

    try {
      const history = [...messages, userMsg]
        .filter((msg) => !msg._streaming)
        .map((msg) => ({ role: msg.role, content: msg.content }));

      const response = await fetch("/api/chat", {
        method: "POST",
        headers: buddyHeaders(),
        body: JSON.stringify({ video_id: videoId, messages: history }),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
          return;
        }
        const err = await response.json().catch(() => ({}));
        setMessages((prev) => [
          ...prev.slice(0, -1),
          { role: "assistant", content: err.error === "not_indexed" ? "Video not indexed yet. Please wait." : "Something went wrong. Please try again." },
        ]);
        setSending(false);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assembled = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
          return;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === "token") {
              assembled += event.text || "";
              if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
                return;
              }
              setMessages((prev) => [
                ...prev.slice(0, -1),
                { role: "assistant", content: assembled, _streaming: true },
              ]);
            } else if (event.type === "status") {
              if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
                return;
              }
              setMessages((prev) => [
                ...prev.slice(0, -1),
                { role: "assistant", content: event.text || "Searching...", _streaming: true, _status: true },
              ]);
            } else if (event.type === "done") {
              if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
                return;
              }
              setMessages((prev) => [
                ...prev.slice(0, -1),
                { role: "assistant", content: assembled },
              ]);
            } else if (event.type === "error") {
              if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
                return;
              }
              setMessages((prev) => [
                ...prev.slice(0, -1),
                { role: "assistant", content: event.text || "Something went wrong. Please try again." },
              ]);
              setSending(false);
              return;
            }
          } catch (e) {
            // Ignore partial or malformed frames.
          }
        }
      }
    } catch (e) {
      if (e && e.name === "AbortError") {
        return;
      }
      if (activeRequestRef.current.id !== requestId || activeRequestRef.current.videoId !== videoId) {
        return;
      }
      setMessages((prev) => [
        ...prev.slice(0, -1),
        { role: "assistant", content: "Network error. Please try again." },
      ]);
    } finally {
      if (activeRequestRef.current.id === requestId) {
        activeRequestRef.current = { id: requestId, videoId: null, controller: null };
        setSending(false);
      }
    }
  }

  if (!summaryDone) {
    return <div className="chat-blocked">Summarize a video first to use AI Chat.</div>;
  }

  if (isDemoVideo) {
    return (
      <div className="chat-container">
        <div className="chat-messages">
          {messages.map((msg, i) => <ChatMessage key={i} msg={msg} />)}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input-row">
          <input
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
            placeholder="Ask anything about this demo video..."
            disabled={sending}
          />
          <button className="chat-send" type="button" onClick={sendMessage} disabled={sending || !input.trim()}>
            {sending ? "..." : "->"}
          </button>
        </div>
      </div>
    );
  }

  if (indexStatus === "idle" || indexStatus === "indexing") {
    return (
      <div className="chat-indexing">
        <div className="chat-indexing__label">Indexing video{indexProgress > 0 ? ` - ${indexProgress}%` : "..."}</div>
        <div className="chat-indexing__bar">
          <div className="chat-indexing__fill" style={{ width: `${indexProgress}%` }} />
        </div>
      </div>
    );
  }

  if (indexStatus === "failed") {
    return (
      <div className="chat-failed">
        <p>{indexError || "Indexing failed."}</p>
        <button type="button" onClick={triggerIndex}>Retry</button>
      </div>
    );
  }

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((msg, i) => <ChatMessage key={i} msg={msg} />)}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
          placeholder="Ask anything about this video..."
          disabled={sending}
        />
        <button className="chat-send" type="button" onClick={sendMessage} disabled={sending || !input.trim()}>
          {sending ? "..." : "->"}
        </button>
      </div>
    </div>
  );
}

window.ChatTab = ChatTab;
