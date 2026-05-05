const { useIndexedStudyFeature, StudyBlocked, StudyIndexing, StudyFailed } = window.__studyFeatureHelpers || {};

function QuizTab({ videoId, summaryDone }) {
  const feature = useIndexedStudyFeature({
    featureKey: "quiz",
    videoId,
    summaryDone,
    endpoint: "/api/quiz",
    createDefaultState: () => ({
      indexStatus: "idle",
      indexProgress: 0,
      indexError: null,
      loading: false,
      error: null,
      payload: { questions: [] },
      metaState: { currentIndex: 0, answers: {} },
    }),
    hasPayload: (payload) => Array.isArray(payload?.questions) && payload.questions.length > 0,
  });

  const questions = Array.isArray(feature.payload?.questions) ? feature.payload.questions : [];
  const currentIndex = Math.min(feature.metaState.currentIndex || 0, Math.max(questions.length - 1, 0));
  const answers = feature.metaState.answers && typeof feature.metaState.answers === "object" ? feature.metaState.answers : {};
  const question = questions[currentIndex];
  const selectedIndex = question ? answers[question.id] : undefined;
  const totalAnswered = questions.filter((item) => Number.isInteger(answers[item.id])).length;
  const score = questions.filter((item) => answers[item.id] === item.correct_index).length;

  const setCurrentIndex = (nextIndex) => {
    feature.setMetaState((prev) => ({ ...prev, currentIndex: nextIndex }));
  };

  const answerQuestion = (optionIndex) => {
    if (!question || Number.isInteger(selectedIndex)) return;
    feature.setMetaState((prev) => ({
      ...prev,
      answers: { ...prev.answers, [question.id]: optionIndex },
    }));
  };

  if (!summaryDone) return <StudyBlocked label="Quiz Me" />;
  if (feature.indexStatus === "idle" || feature.indexStatus === "indexing") {
    return <StudyIndexing label="Quiz Me" progress={feature.indexProgress} />;
  }
  if (feature.indexStatus === "failed") {
    return <StudyFailed message={feature.indexError} onRetry={feature.triggerIndex} />;
  }

  if (feature.loading && questions.length === 0) {
    return <div className="study-loading">Building quiz questions from the transcript...</div>;
  }

  if (feature.error && questions.length === 0) {
    return (
      <div className="study-failed">
        <p>{feature.error}</p>
        <button type="button" onClick={feature.reloadFeature}>Try again</button>
      </div>
    );
  }

  if (!question) {
    return <div className="study-empty">No quiz questions were generated for this video yet.</div>;
  }

  return (
    <div className="study-shell">
      <div className="study-toolbar">
        <div>
          <div className="study-progress mono">QUESTION {String(currentIndex + 1).padStart(2, "0")} / {String(questions.length).padStart(2, "0")}</div>
          <div className="study-score">Score {score}/{questions.length} - Answered {totalAnswered}/{questions.length}</div>
        </div>
        <button type="button" className="export-btn" onClick={feature.reloadFeature} disabled={feature.loading}>
          {feature.loading ? "Refreshing..." : "Refresh quiz"}
        </button>
      </div>

      <div className="quiz-card">
        <div className="quiz-card__prompt">{question.prompt}</div>
        <div className="quiz-options">
          {question.options.map((option, optionIndex) => {
            const isSelected = selectedIndex === optionIndex;
            const isCorrect = optionIndex === question.correct_index;
            const stateClass = Number.isInteger(selectedIndex)
              ? (isCorrect ? "is-correct" : (isSelected ? "is-wrong" : ""))
              : "";
            return (
              <button
                key={`${question.id}-${optionIndex}`}
                type="button"
                className={`quiz-option ${isSelected ? "is-selected" : ""} ${stateClass}`}
                onClick={() => answerQuestion(optionIndex)}
                disabled={Number.isInteger(selectedIndex)}
              >
                <span className="quiz-option__marker mono">{String.fromCharCode(65 + optionIndex)}</span>
                <span>{option}</span>
              </button>
            );
          })}
        </div>

        {Number.isInteger(selectedIndex) ? (
          <div className="quiz-feedback">
            <div className="quiz-feedback__status">
              {selectedIndex === question.correct_index ? "Correct" : "Incorrect"}
            </div>
            <p>{question.explanation}</p>
            <button
              type="button"
              className="chat-timestamp-chip"
              onClick={() => window.__scrollTranscriptTo && window.__scrollTranscriptTo(question.timestamp)}
            >
              ~{question.timestamp}
            </button>
          </div>
        ) : null}
      </div>

      <div className="study-actions">
        <button type="button" className="export-btn" onClick={() => setCurrentIndex((currentIndex - 1 + questions.length) % questions.length)} disabled={questions.length < 2}>
          Previous
        </button>
        <button type="button" className="study-primary-btn" onClick={() => setCurrentIndex((currentIndex + 1) % questions.length)} disabled={questions.length < 2}>
          Next question
        </button>
      </div>
    </div>
  );
}

window.QuizTab = QuizTab;
