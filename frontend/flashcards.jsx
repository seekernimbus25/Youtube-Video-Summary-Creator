const {
  useState: useStudyState,
  useEffect: useStudyEffect,
  useRef: useStudyRef,
  useCallback: useStudyCallback,
} = React;

const studyFeatureCache = new Map();

function studyBuddyHeaders() {
  const headers = { "Content-Type": "application/json" };
  const apiKey = sessionStorage.getItem("buddy_api_key");
  const provider = sessionStorage.getItem("buddy_provider");
  const model = sessionStorage.getItem("buddy_model");
  if (apiKey) headers["X-Buddy-Api-Key"] = apiKey;
  if (provider) headers["X-Buddy-Provider"] = provider;
  if (model) headers["X-Buddy-Model"] = model;
  return headers;
}

function getStudyStorageKey(featureKey, videoId) {
  return `yt-distiller-study:${featureKey}:${videoId}`;
}

function loadStoredStudyState(featureKey, videoId, defaults) {
  if (!videoId) return defaults;

  const cacheKey = `${featureKey}:${videoId}`;
  if (studyFeatureCache.has(cacheKey)) {
    return studyFeatureCache.get(cacheKey);
  }

  try {
    const raw = sessionStorage.getItem(getStudyStorageKey(featureKey, videoId));
    if (!raw) return defaults;
    const parsed = JSON.parse(raw);
    const next = {
      ...defaults,
      ...parsed,
      // Never restore in-flight request state after a refresh.
      loading: false,
    };
    studyFeatureCache.set(cacheKey, next);
    return next;
  } catch (e) {
    sessionStorage.removeItem(getStudyStorageKey(featureKey, videoId));
    return defaults;
  }
}

function persistStudyState(featureKey, videoId, nextState) {
  if (!videoId) return;
  const cacheKey = `${featureKey}:${videoId}`;
  studyFeatureCache.set(cacheKey, nextState);
  try {
    sessionStorage.setItem(getStudyStorageKey(featureKey, videoId), JSON.stringify(nextState));
  } catch (e) {
    // Ignore storage failures and keep the in-memory state usable.
  }
}

function useIndexedStudyFeature({ featureKey, videoId, summaryDone, endpoint, createDefaultState, hasPayload }) {
  const defaultsRef = useStudyRef(null);
  const hasPayloadRef = useStudyRef(hasPayload);
  if (!defaultsRef.current) {
    defaultsRef.current = createDefaultState();
  }
  hasPayloadRef.current = hasPayload;

  const initialState = loadStoredStudyState(featureKey, videoId, defaultsRef.current);
  const [indexStatus, setIndexStatus] = useStudyState(initialState.indexStatus);
  const [indexProgress, setIndexProgress] = useStudyState(initialState.indexProgress);
  const [indexError, setIndexError] = useStudyState(initialState.indexError);
  const [loading, setLoading] = useStudyState(initialState.loading);
  const [error, setError] = useStudyState(initialState.error);
  const [payload, setPayload] = useStudyState(initialState.payload);
  const [metaState, setMetaState] = useStudyState(initialState.metaState);
  const pollRef = useStudyRef(null);
  const statusSyncRef = useStudyRef(false);
  const requestSeqRef = useStudyRef(0);
  const activeFeatureRequestRef = useStudyRef(null);

  const nextRequestToken = useStudyCallback(() => {
    requestSeqRef.current += 1;
    return requestSeqRef.current;
  }, []);

  const isActiveToken = useStudyCallback((token) => token === requestSeqRef.current, []);

  const cancelFeatureRequest = useStudyCallback(() => {
    if (activeFeatureRequestRef.current) {
      activeFeatureRequestRef.current.abort();
      activeFeatureRequestRef.current = null;
    }
  }, []);

  const clearPolling = useStudyCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useStudyCallback((vid) => {
    if (pollRef.current) return;
    const token = requestSeqRef.current;
    pollRef.current = setInterval(async () => {
      try {
        const response = await fetch(`/api/index/status?video_id=${vid}`);
        const data = await response.json();
        if (!isActiveToken(token)) return;
        if (data.status === "ready") {
          clearPolling();
          setIndexStatus("ready");
        } else if (data.status === "failed") {
          clearPolling();
          setIndexStatus("failed");
          setIndexError(data.message || data.error || "Indexing failed");
        } else if (data.status === "indexing") {
          setIndexProgress(data.progress_pct || 0);
        }
      } catch (e) {
        // Keep polling through transient failures.
      }
    }, 5000);
  }, [clearPolling, isActiveToken]);

  useStudyEffect(() => () => {
    clearPolling();
    cancelFeatureRequest();
  }, [cancelFeatureRequest, clearPolling]);

  useStudyEffect(() => {
    clearPolling();
    cancelFeatureRequest();
    nextRequestToken();
    const next = loadStoredStudyState(featureKey, videoId, defaultsRef.current);
    setIndexStatus(next.indexStatus);
    setIndexProgress(next.indexProgress);
    setIndexError(next.indexError);
    setLoading(next.loading);
    setError(next.error);
    setPayload(next.payload);
    setMetaState(next.metaState);
    statusSyncRef.current = false;
  }, [cancelFeatureRequest, clearPolling, featureKey, nextRequestToken, videoId]);

  useStudyEffect(() => {
    persistStudyState(featureKey, videoId, {
      indexStatus,
      indexProgress,
      indexError,
      loading,
      error,
      payload,
      metaState,
    });
  }, [videoId, featureKey, indexStatus, indexProgress, indexError, loading, error, payload, metaState]);

  const triggerIndex = useStudyCallback(async () => {
    if (!videoId || !summaryDone) return;
    const token = requestSeqRef.current;
    setIndexStatus("indexing");
    setIndexError(null);
    try {
      const response = await fetch("/api/index", {
        method: "POST",
        headers: studyBuddyHeaders(),
        body: JSON.stringify({ video_id: videoId }),
      });
      if (!isActiveToken(token)) return;
      if (response.status === 200) {
        setIndexStatus("ready");
      } else if (response.status === 202) {
        startPolling(videoId);
      } else {
        const data = await response.json().catch(() => ({}));
        setIndexStatus("failed");
        setIndexError(data.message || "Indexing service unavailable. Please try again.");
      }
    } catch (e) {
      if (!isActiveToken(token)) return;
      setIndexStatus("failed");
      setIndexError("Network error. Please try again.");
    }
  }, [isActiveToken, videoId, summaryDone, startPolling]);

  const syncIndexStatus = useStudyCallback(async () => {
    if (!videoId || !summaryDone || statusSyncRef.current) return;
    statusSyncRef.current = true;
    const token = requestSeqRef.current;
    try {
      const response = await fetch(`/api/index/status?video_id=${videoId}`);
      const data = await response.json().catch(() => ({}));
      if (!isActiveToken(token)) return;
      if (data.status === "ready") {
        setIndexStatus("ready");
        setIndexProgress(100);
        setIndexError(null);
        return;
      }
      if (data.status === "indexing") {
        setIndexStatus("indexing");
        setIndexProgress(data.progress_pct || 0);
        setIndexError(null);
        startPolling(videoId);
        return;
      }
      if (data.status === "failed") {
        setIndexStatus("failed");
        setIndexError(data.message || data.error || "Indexing failed");
        return;
      }
      triggerIndex();
    } catch (e) {
      if (!isActiveToken(token)) return;
      triggerIndex();
    }
  }, [isActiveToken, summaryDone, triggerIndex, videoId, startPolling]);

  const loadFeature = useStudyCallback(async (force = false) => {
    if (!videoId || !summaryDone || loading) return;
    if (!force && hasPayloadRef.current(payload)) return;
    const token = requestSeqRef.current;
    cancelFeatureRequest();
    const controller = new AbortController();
    activeFeatureRequestRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: studyBuddyHeaders(),
        body: JSON.stringify({ video_id: videoId }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!isActiveToken(token) || activeFeatureRequestRef.current !== controller) return;
      if (!response.ok) {
        setError(data.message || (data.error === "not_indexed" ? "Video not indexed yet. Please wait." : "Could not generate this study view."));
      } else {
        setPayload(data);
      }
    } catch (e) {
      if (e?.name === "AbortError") return;
      if (!isActiveToken(token) || activeFeatureRequestRef.current !== controller) return;
      setError("Network error. Please try again.");
    } finally {
      if (activeFeatureRequestRef.current === controller) {
        activeFeatureRequestRef.current = null;
      }
      if (isActiveToken(token)) {
        setLoading(false);
      }
    }
  }, [cancelFeatureRequest, endpoint, isActiveToken, loading, payload, summaryDone, videoId]);

  useStudyEffect(() => {
    if (indexStatus === "idle" && summaryDone && videoId) {
      syncIndexStatus();
    }
  }, [indexStatus, summaryDone, videoId, syncIndexStatus]);

  useStudyEffect(() => {
    if (indexStatus === "indexing" && videoId) {
      startPolling(videoId);
    }
  }, [indexStatus, videoId, startPolling]);

  useStudyEffect(() => {
    if (indexStatus === "ready" && summaryDone && videoId && !loading && !hasPayloadRef.current(payload)) {
      loadFeature(false);
    }
  }, [indexStatus, loadFeature, loading, payload, summaryDone, videoId]);

  return {
    indexStatus,
    indexProgress,
    indexError,
    loading,
    error,
    payload,
    setPayload,
    metaState,
    setMetaState,
    triggerIndex,
    reloadFeature: () => loadFeature(true),
  };
}

function StudyBlocked({ label }) {
  return <div className="chat-blocked">Summarize a video first to use {label}.</div>;
}

function StudyIndexing({ label, progress }) {
  return (
    <div className="chat-indexing">
      <div className="chat-indexing__label">Indexing video for {label}{progress > 0 ? ` - ${progress}%` : "..."}</div>
      <div className="chat-indexing__bar">
        <div className="chat-indexing__fill" style={{ width: `${progress}%` }} />
      </div>
    </div>
  );
}

function StudyFailed({ message, onRetry }) {
  return (
    <div className="chat-failed">
      <p>{message || "Indexing failed."}</p>
      <button type="button" onClick={onRetry}>Retry</button>
    </div>
  );
}

function FlashcardsTab({ videoId, summaryDone }) {
  const feature = useIndexedStudyFeature({
    featureKey: "flashcards",
    videoId,
    summaryDone,
    endpoint: "/api/flashcards",
    createDefaultState: () => ({
      indexStatus: "idle",
      indexProgress: 0,
      indexError: null,
      loading: false,
      error: null,
      payload: { cards: [] },
      metaState: { currentIndex: 0, revealed: false },
    }),
    hasPayload: (payload) => Array.isArray(payload?.cards) && payload.cards.length > 0,
  });

  const cards = Array.isArray(feature.payload?.cards) ? feature.payload.cards : [];
  const currentIndex = Math.min(feature.metaState.currentIndex || 0, Math.max(cards.length - 1, 0));
  const revealed = !!feature.metaState.revealed;
  const card = cards[currentIndex];

  const setCurrentIndex = (nextIndex) => {
    feature.setMetaState((prev) => ({ ...prev, currentIndex: nextIndex, revealed: false }));
  };

  if (!summaryDone) return <StudyBlocked label="Flashcards" />;
  if (feature.indexStatus === "idle" || feature.indexStatus === "indexing") {
    return <StudyIndexing label="Flashcards" progress={feature.indexProgress} />;
  }
  if (feature.indexStatus === "failed") {
    return <StudyFailed message={feature.indexError} onRetry={feature.triggerIndex} />;
  }

  if (feature.loading && cards.length === 0) {
    return <div className="study-loading">Generating flashcards from the transcript...</div>;
  }

  if (feature.error && cards.length === 0) {
    return (
      <div className="study-failed">
        <p>{feature.error}</p>
        <button type="button" onClick={feature.reloadFeature}>Try again</button>
      </div>
    );
  }

  if (!card) {
    return <div className="study-empty">No flashcards were generated for this video yet.</div>;
  }

  return (
    <div className="study-shell">
      <div className="study-toolbar">
        <div className="study-progress mono">CARD {String(currentIndex + 1).padStart(2, "0")} / {String(cards.length).padStart(2, "0")}</div>
        <button type="button" className="export-btn" onClick={feature.reloadFeature} disabled={feature.loading}>
          {feature.loading ? "Refreshing..." : "Refresh deck"}
        </button>
      </div>

      <div className={`flashcard ${revealed ? "is-revealed" : ""}`}>
        <div className="flashcard-panel">
          <div className="flashcard-panel__label">{revealed ? "ANSWER" : "PROMPT"}</div>
          <div className="flashcard-panel__content">{revealed ? card.back : card.front}</div>
        </div>
        <div className="flashcard-meta">
          <span className="tag">{card.topic || "Study"}</span>
          <button
            type="button"
            className="chat-timestamp-chip"
            onClick={() => window.__scrollTranscriptTo && window.__scrollTranscriptTo(card.timestamp)}
          >
            ~{card.timestamp}
          </button>
        </div>
      </div>

      <div className="study-actions">
        <button type="button" className="export-btn" onClick={() => setCurrentIndex((currentIndex - 1 + cards.length) % cards.length)} disabled={cards.length < 2}>
          Previous
        </button>
        <button
          type="button"
          className="study-primary-btn"
          onClick={() => feature.setMetaState((prev) => ({ ...prev, revealed: !prev.revealed }))}
        >
          {revealed ? "Hide answer" : "Reveal answer"}
        </button>
        <button type="button" className="export-btn" onClick={() => setCurrentIndex((currentIndex + 1) % cards.length)} disabled={cards.length < 2}>
          Next
        </button>
      </div>
    </div>
  );
}

window.__studyFeatureHelpers = {
  useIndexedStudyFeature,
  StudyBlocked,
  StudyIndexing,
  StudyFailed,
};

window.FlashcardsTab = FlashcardsTab;
