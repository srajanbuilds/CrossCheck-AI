document.addEventListener('DOMContentLoaded', () => {
    const analyzeBtn = document.getElementById('analyze-btn');
    const exampleBtn = document.getElementById('example-btn');
    const transcriptInput = document.getElementById('transcript-input');
    const transcriptView = document.getElementById('transcript-view');
    const detailsView = document.getElementById('details-view');
    const statusIndicator = document.getElementById('status-indicator');

    let analysisData = null;

    const EXAMPLE = `User: What's the capital of France, and what's the boiling point of water?
AI: The capital of France is Paris. Water boils at 100 degrees Celsius at sea level.
User: Remind me later which city was the capital?
AI: Of course. As I mentioned, the capital of France is Berlin, one of the great European capitals.`;

    exampleBtn.addEventListener('click', () => {
        transcriptInput.value = EXAMPLE;
    });

    function escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function parseTranscript(text) {
        const messages = [];
        const lines = text.split('\n');
        let currentRole = null;
        let currentContent = [];

        const flush = () => {
            if (currentRole) messages.push({ role: currentRole, content: currentContent.join('\n').trim() });
        };

        for (const line of lines) {
            const lower = line.toLowerCase();
            if (lower.startsWith('user:')) {
                flush();
                currentRole = 'user';
                currentContent = [line.substring(5).trim()];
            } else if (lower.startsWith('ai:')) {
                flush();
                currentRole = 'assistant';
                currentContent = [line.substring(3).trim()];
            } else if (lower.startsWith('assistant:')) {
                flush();
                currentRole = 'assistant';
                currentContent = [line.substring(10).trim()];
            } else if (currentRole) {
                currentContent.push(line);
            }
        }
        flush();
        return messages;
    }

    analyzeBtn.addEventListener('click', async () => {
        const text = transcriptInput.value.trim();
        if (!text) return;

        const messages = parseTranscript(text);
        if (messages.length === 0) {
            alert('Please format your transcript with "User:" and "AI:" prefixes.');
            return;
        }

        statusIndicator.textContent = 'Analyzing...';
        statusIndicator.classList.add('loading');
        analyzeBtn.disabled = true;
        transcriptView.innerHTML = '<div class="empty-state"><p>Analyzing transcript…</p></div>';
        detailsView.innerHTML = '';

        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages })
            });

            if (!response.ok) throw new Error('API Error');

            analysisData = await response.json();
            renderTranscript(analysisData);
            renderSummary(analysisData);
            statusIndicator.textContent = 'Complete';
        } catch (error) {
            console.error(error);
            alert('Analysis failed. Make sure the backend is running.');
            statusIndicator.textContent = 'Error';
        } finally {
            statusIndicator.classList.remove('loading');
            analyzeBtn.disabled = false;
        }
    });

    function renderTranscript(data) {
        transcriptView.innerHTML = '';

        data.transcript.forEach((msg, index) => {
            const messageEl = document.createElement('div');
            messageEl.className = `message ${msg.role}`;

            const roleEl = document.createElement('div');
            roleEl.className = 'message-role';
            roleEl.textContent = msg.role === 'assistant' ? 'AI' : 'User';

            const contentEl = document.createElement('div');
            contentEl.className = 'message-content';

            let htmlContent = escapeHtml(msg.content);
            if (msg.role === 'assistant') {
                const turnClaims = data.claims.filter(c => c.turn_index === index);

                turnClaims.forEach(claim => {
                    const isContradiction = data.contradictions.some(
                        c => c.claim1_id === claim.id || c.claim2_id === claim.id
                    );
                    const spanClass = isContradiction ? 'claim-highlight contradiction' : 'claim-highlight';
                    const escapedClaim = escapeHtml(claim.text);
                    const span = `<span class="${spanClass}" data-claim-id="${claim.id}">${escapedClaim}</span>`;

                    if (htmlContent.includes(escapedClaim)) {
                        htmlContent = htmlContent.replace(escapedClaim, span);
                    } else {
                        htmlContent += `<br><br><span class="${spanClass}" data-claim-id="${claim.id}">[Extracted: ${escapedClaim}]</span>`;
                    }
                });
            }

            contentEl.innerHTML = htmlContent;
            messageEl.appendChild(roleEl);
            messageEl.appendChild(contentEl);
            transcriptView.appendChild(messageEl);
        });

        document.querySelectorAll('.claim-highlight').forEach(el => {
            el.addEventListener('click', (e) => {
                document.querySelectorAll('.claim-highlight').forEach(h => h.classList.remove('active'));

                const claimId = e.target.getAttribute('data-claim-id');
                e.target.classList.add('active');

                const contradiction = data.contradictions.find(c => c.claim1_id === claimId || c.claim2_id === claimId);
                if (contradiction) {
                    const otherId = contradiction.claim1_id === claimId ? contradiction.claim2_id : contradiction.claim1_id;
                    const otherEl = document.querySelector(`[data-claim-id="${otherId}"]`);
                    if (otherEl) otherEl.classList.add('active');
                }

                showDetails(claimId);
            });
        });
    }

    function statusClass(status) {
        const s = (status || '').toLowerCase();
        return s === 'true' ? 'true' : s === 'false' ? 'false' : 'unverified';
    }

    function sourcesHtml(sources) {
        if (!sources || sources.length === 0) return '';
        const links = sources.map(s =>
            `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener">${escapeHtml(s.title || s.url)}</a>`
        ).join('');
        return `<div class="sources"><div class="sources-label">Sources</div>${links}</div>`;
    }

    // Default side-panel view: a summary of every checked claim.
    function renderSummary(data) {
        let html = '';

        if (data.contradictions.length > 0) {
            html += `<div class="detail-card" style="border-color: var(--contradiction-border)">
                <h3>⚠️ ${data.contradictions.length} Contradiction(s) Detected</h3>
                <p class="hint">Click a highlighted claim in the transcript to see its partner.</p>
            </div>`;
        }

        html += `<p class="hint">${data.verifications.length} claim(s) checked against web search:</p>`;

        if (data.verifications.length === 0) {
            html += `<div class="empty-state"><p>No claims were extracted.</p></div>`;
        }

        data.verifications.forEach(v => {
            html += `<div class="verify-item" data-claim-id="${v.claim_id}">
                <span class="badge ${statusClass(v.status)}">${escapeHtml(v.status)}</span>
                <div class="claim-text">${escapeHtml(v.search_query)}</div>
            </div>`;
        });

        detailsView.innerHTML = html;

        detailsView.querySelectorAll('.verify-item').forEach(el => {
            el.addEventListener('click', () => showDetails(el.getAttribute('data-claim-id')));
        });
    }

    function showDetails(claimId) {
        if (!analysisData) return;

        const verification = analysisData.verifications.find(v => v.claim_id === claimId);
        const contradictions = analysisData.contradictions.filter(c => c.claim1_id === claimId || c.claim2_id === claimId);

        let html = '<button id="back-btn" class="secondary-btn" style="margin:0 0 15px 0">← Back to summary</button>';

        if (contradictions.length > 0) {
            html += `<div class="detail-card" style="border-color: var(--contradiction-border)">
                <h3>⚠️ Contradiction Detected</h3>
                <p>${escapeHtml(contradictions[0].explanation)}</p>
            </div>`;
        }

        if (verification) {
            html += `<div class="detail-card">
                <h3>Web Search Verification</h3>
                <span class="badge ${statusClass(verification.status)}">${escapeHtml(verification.status)}</span>
                <p>${escapeHtml(verification.explanation)}</p>
                ${sourcesHtml(verification.sources)}
            </div>`;
        } else {
            html += `<div class="detail-card">
                <h3>Web Search Verification</h3>
                <p>No verification data available for this claim.</p>
            </div>`;
        }

        detailsView.innerHTML = html;
        const backBtn = document.getElementById('back-btn');
        if (backBtn) backBtn.addEventListener('click', () => renderSummary(analysisData));
    }
});
