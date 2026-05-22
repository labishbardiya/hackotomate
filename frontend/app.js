/* -------------------------------------------------------------
 * OCEAN // DYNAMIC TERMINAL CONTROLLER
 * Asynchronous data streams, real-time log parsing & animations
 * ------------------------------------------------------------- */

document.addEventListener("DOMContentLoaded", () => {
    // ---------------------------------------------------------
    // Application State
    // ---------------------------------------------------------
    let hackathons = [];
    let tracks = [];
    let activeTrack = "all";
    let activeSearch = "";

    // ---------------------------------------------------------
    // DOM Node Cache
    // ---------------------------------------------------------
    const nodes = {
        grid: document.getElementById("hackathons-grid"),
        tracksScroller: document.getElementById("tracks-scroller"),
        searchInput: document.getElementById("search-input"),
        btnClearSearch: document.getElementById("btn-clear-search"),
        btnRunPipeline: document.getElementById("btn-run-pipeline"),
        btnResetDb: document.getElementById("btn-reset-db"),
        trackBanner: document.getElementById("track-banner"),
        trackBannerTitle: document.getElementById("track-banner-title"),
        trackBannerDesc: document.getElementById("track-banner-desc"),
        emptyState: document.getElementById("empty-state"),
        statusIndicator: document.getElementById("status-indicator"),
        statusText: document.getElementById("status-text"),
        logConsole: document.getElementById("log-console-panel"),
        consoleTrigger: document.getElementById("console-trigger"),
        consoleOutput: document.getElementById("console-output"),
        btnCloseConsole: document.getElementById("btn-close-console"),
        toastContainer: document.getElementById("toast-container")
    };

    // ---------------------------------------------------------
    // Toast Notification System
    // ---------------------------------------------------------
    function showToast(message, type = "success") {
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        toast.innerHTML = `<span class="toast-indicator"></span> ${message}`;
        nodes.toastContainer.appendChild(toast);
        
        // Auto-cleanup after animation ends (3s total)
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    // ---------------------------------------------------------
    // Database Core API Sync
    // ---------------------------------------------------------
    async function syncSystem() {
        try {
            updateStatus("syncing", "SYNC_DATA");
            
            // Parallel fetches from Supabase PostgreSQL via server endpoints
            const [hackathonsRes, tracksRes] = await Promise.all([
                fetch(`/api/hackathons?track=${activeTrack}`),
                fetch("/api/tracks")
            ]);

            if (!hackathonsRes.ok || !tracksRes.ok) {
                throw new Error(`HTTP sync faulted: ${hackathonsRes.status} / ${tracksRes.status}`);
            }

            hackathons = await hackathonsRes.json();
            tracks    = await tracksRes.json();

            if (!Array.isArray(hackathons)) hackathons = [];
            if (!Array.isArray(tracks))     tracks     = [];
            
            updateStatus("connected", "SYS_ONLINE");
            
            renderTrackTabs();
            renderHackathons();
            renderTrackBanner();
            
        } catch (error) {
            console.error("[-] API Sync error:", error);
            updateStatus("offline", "SYS_FAULT");
            showToast("System synchronization failure", "error");
            renderEmptyState();
        }
    }

    function updateStatus(state, label) {
        nodes.statusIndicator.className = `status-badge ${state}`;
        nodes.statusText.textContent = label;
    }

    // ---------------------------------------------------------
    // Track Banner Manager
    // ---------------------------------------------------------
    function renderTrackBanner() {
        if (activeTrack === "all") {
            nodes.trackBanner.style.display = "none";
            return;
        }
        
        const current = tracks.find(t => t.slug === activeTrack);
        if (current) {
            nodes.trackBannerTitle.textContent = current.display_name;
            nodes.trackBannerDesc.textContent = current.summary || "Dynamically grouped tech frontiers.";
            nodes.trackBanner.style.display = "block";
        } else {
            nodes.trackBanner.style.display = "none";
        }
    }

    // ---------------------------------------------------------
    // Render Track Selection Navigation
    // ---------------------------------------------------------
    function renderTrackTabs() {
        nodes.tracksScroller.innerHTML = "";
        
        // [View All] Tab
        const allTab = document.createElement("button");
        allTab.className = `category-tab ${activeTrack === "all" ? "active" : ""}`;
        allTab.textContent = "[View All]";
        allTab.addEventListener("click", () => selectTrack("all"));
        nodes.tracksScroller.appendChild(allTab);
        
        // Dynamic DB Tabs
        tracks.forEach(track => {
            const tab = document.createElement("button");
            tab.className = `category-tab ${activeTrack === track.slug ? "active" : ""}`;
            tab.textContent = `[${track.display_name}]`;
            tab.addEventListener("click", () => selectTrack(track.slug));
            nodes.tracksScroller.appendChild(tab);
        });
    }

    function selectTrack(slug) {
        if (activeTrack === slug) return;
        activeTrack = slug;
        syncSystem();
    }

    // ---------------------------------------------------------
    // Render Hackathon Cards List
    // ---------------------------------------------------------
    function renderHackathons() {
        nodes.grid.innerHTML = "";
        
        // Apply frontend search query filter
        const filtered = hackathons.filter(h => {
            if (!activeSearch) return true;
            const query = activeSearch.toLowerCase();
            const tagsText = Array.isArray(h.tags) ? h.tags.join(" ") : "";
            return (
                h.name.toLowerCase().includes(query) ||
                (h.organizer || "").toLowerCase().includes(query) ||
                (h.description_summary || "").toLowerCase().includes(query) ||
                tagsText.toLowerCase().includes(query)
            );
        });
        
        if (filtered.length === 0) {
            renderEmptyState();
            return;
        }
        
        nodes.emptyState.style.display = "none";
        nodes.grid.style.display = "grid";
        
        filtered.forEach(h => {
            const card = document.createElement("div");
            card.className = "hackathon-card";
            
            // Format dynamic deadlines
            const deadlineText = formatDeadline(h.registration_deadline);
            const deadlineClass = getDeadlineClass(h.registration_deadline);
            
            // Format prize pool
            const prizeText = h.prize_pool || "REWARDS LISTED";
            
            // Map tags
            const tagsHTML = (h.tags || []).slice(0, 4).map(t => `<span class="tag-pill">#${t.toLowerCase()}</span>`).join("");
            
            card.innerHTML = `
                <div>
                    <div class="card-header">
                        <span class="organizer-tag" title="${h.organizer || 'Independent'}">${h.organizer || 'Independent'}</span>
                        <span class="prize-badge">${prizeText}</span>
                    </div>
                    <h2 class="card-title" title="${h.name}">${h.name}</h2>
                    <p class="card-desc" title="${h.description_summary}">${h.description_summary || 'Ingested hackathon node catalogued.'}</p>
                    
                    <div class="card-meta-list">
                        <div class="meta-row">
                            <span class="meta-label">Timeline:</span>
                            <span class="meta-val">${formatDate(h.start_date)} ➔ ${formatDate(h.end_date)}</span>
                        </div>
                        <div class="meta-row">
                            <span class="meta-label">Apply By:</span>
                            <span class="meta-val deadline ${deadlineClass}">${deadlineText}</span>
                        </div>
                    </div>
                    
                    <div class="card-tags">
                        ${tagsHTML}
                    </div>
                </div>
                
                <div class="card-actions">
                    <a href="${h.registration_url}" target="_blank" class="btn btn-primary btn-launch font-mono text-uppercase">
                        LAUNCH_PORTAL ↗
                    </a>
                    <button class="btn btn-sec btn-share" data-title="${h.name}" data-url="${h.registration_url}">
                        📤
                    </button>
                </div>
            `;
            
            // Hook Share Button
            const btnShare = card.querySelector(".btn-share");
            btnShare.addEventListener("click", (e) => {
                e.preventDefault();
                shareHackathon(h.name, h.registration_url);
            });
            
            nodes.grid.appendChild(card);
        });
    }

    function renderEmptyState() {
        nodes.grid.style.display = "none";
        nodes.emptyState.style.display = "block";
    }

    // ---------------------------------------------------------
    // Timeline Meta Format Helpers
    // ---------------------------------------------------------
    function formatDate(dateStr) {
        if (!dateStr) return "TBD";
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return dateStr;
            return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        } catch {
            return dateStr;
        }
    }

    function formatDeadline(deadlineStr) {
        if (!deadlineStr) return "OPEN REGISTRATION";
        try {
            const deadline = new Date(deadlineStr);
            if (isNaN(deadline.getTime())) return deadlineStr;
            
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            const diffTime = deadline - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) {
                return "CLOSED";
            } else if (diffDays === 0) {
                return "TODAY (URGENT)";
            } else if (diffDays === 1) {
                return "1 DAY REMAINING";
            } else if (diffDays <= 5) {
                return `${diffDays} DAYS REMAINING`;
            } else {
                return deadline.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
            }
        } catch {
            return deadlineStr;
        }
    }

    function getDeadlineClass(deadlineStr) {
        if (!deadlineStr) return "";
        try {
            const deadline = new Date(deadlineStr);
            if (isNaN(deadline.getTime())) return "";
            
            const today = new Date();
            today.setHours(0, 0, 0, 0);
            
            const diffTime = deadline - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) {
                return "closed";
            } else if (diffDays === 0 || diffDays === 1) {
                return "urgent";
            } else if (diffDays <= 5) {
                return "warning";
            }
        } catch {}
        return "";
    }

    // ---------------------------------------------------------
    // Web Share API Integration
    // ---------------------------------------------------------
    async function shareHackathon(title, url) {
        if (navigator.share) {
            try {
                await navigator.share({
                    title: `Ocean Hackathon: ${title}`,
                    text: `Check out this automated hackathon listing on Ocean: ${title}`,
                    url: url
                });
                showToast("Node shared successfully");
            } catch (error) {
                if (error.name !== "AbortError") {
                    copyToClipboard(url);
                }
            }
        } else {
            copyToClipboard(url);
        }
    }

    function copyToClipboard(text) {
        navigator.clipboard.writeText(text).then(() => {
            showToast("Registration link copied to clipboard");
        }).catch(() => {
            showToast("Failed to copy link", "error");
        });
    }

    // ---------------------------------------------------------
    // Dynamic Fuzzy Search Filter
    // ---------------------------------------------------------
    nodes.searchInput.addEventListener("input", (e) => {
        activeSearch = e.target.value;
        if (activeSearch) {
            nodes.btnClearSearch.style.display = "block";
        } else {
            nodes.btnClearSearch.style.display = "none";
        }
        renderHackathons();
    });

    nodes.btnClearSearch.addEventListener("click", () => {
        nodes.searchInput.value = "";
        activeSearch = "";
        nodes.btnClearSearch.style.display = "none";
        renderHackathons();
    });

    // ---------------------------------------------------------
    // Ingestion Log Stream (SSE/Streaming) Trigger
    // ---------------------------------------------------------
    nodes.btnRunPipeline.addEventListener("click", async () => {
        // Double-tap prevention
        if (nodes.btnRunPipeline.disabled) return;
        
        nodes.btnRunPipeline.disabled = true;
        nodes.btnRunPipeline.style.opacity = 0.5;
        
        // Open log terminal and mark active
        nodes.logConsole.className = "log-console-panel expanded active";
        nodes.consoleOutput.innerHTML = "";
        
        appendLogLine("[*] LAUNCHING DISTRIBUTED CRAWLER INGESTION LAYER...", "cyan");
        appendLogLine("[*] Connection Parameters: Ingestion engine active (NVIDIA NIM with Local Fallback)", "gold");
        
        try {
            updateStatus("syncing", "CRAWL_RUN");

            // Check if user entered a specific URL in search input to ingest
            const searchValue = nodes.searchInput.value.trim();
            const isUrl = searchValue.startsWith("http://") || searchValue.startsWith("https://");
            
            let runUrl = "/api/pipeline/run";
            if (isUrl) {
                runUrl += `?url=${encodeURIComponent(searchValue)}`;
                appendLogLine(`[+] Direct URL Ingestion mode triggered for: ${searchValue}`, "cyan");
            }

            // Build headers – include admin key if configured in meta tag
            const adminKey = document.querySelector('meta[name="admin-key"]')?.content || "";
            const headers  = adminKey ? { "x-admin-key": adminKey } : {};

            const response = await fetch(runUrl, { headers });
            
            if (!response.ok) {
                throw new Error(`Pipeline returned HTTP status ${response.status}`);
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let partialChunk = "";
            
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                
                const chunk = decoder.decode(value, { stream: true });
                const lines = (partialChunk + chunk).split("\n");
                partialChunk = lines.pop(); // Hold remaining split line
                
                for (const line of lines) {
                    if (line.trim()) {
                        parseAndAppendLogLine(line);
                    }
                }
            }
            
            if (partialChunk.trim()) {
                parseAndAppendLogLine(partialChunk);
            }
            
            appendLogLine("\n[+] INGESTION PIPELINE TERMINATED SUCCESSFULLY.", "green");
            showToast("Aggregator pipeline complete");

        } catch (error) {
            console.error(error);
            appendLogLine(`\n[!] PIPELINE EXCEPTION: ${error.message}`, "red");
            showToast("Pipeline encountered an error", "error");
        } finally {
            // Re-enable trigger button
            nodes.btnRunPipeline.disabled = false;
            nodes.btnRunPipeline.style.opacity = 1;
            // Collapse active pulsing on log panel
            nodes.logConsole.className = "log-console-panel expanded";

            // ── Implicit layout revalidation on stream close ───────────────
            // Reset UI filter state before syncing so the grid shows fresh data
            activeTrack  = "all";
            activeSearch = "";
            nodes.searchInput.value = "";
            nodes.btnClearSearch.style.display = "none";

            appendLogLine("[*] Revalidating Supabase endpoints...", "cyan");
            await syncSystem();
            appendLogLine("[+] Grid revalidation complete.", "green");
        }
    });

    function parseAndAppendLogLine(line) {
        let colorClass = "";
        if (line.startsWith("[+]")) {
            colorClass = "green";
        } else if (line.startsWith("[-]")) {
            colorClass = "red";
        } else if (line.startsWith("[~]") || line.startsWith("[!]")) {
            colorClass = "gold";
        } else if (line.startsWith("[*]")) {
            colorClass = "cyan";
        }
        appendLogLine(line, colorClass);
    }

    function appendLogLine(text, colorClass = "") {
        const line = document.createElement("div");
        line.className = `log-line font-mono ${colorClass}`;
        line.textContent = text;
        nodes.consoleOutput.appendChild(line);
        
        // Scroll terminal console down
        nodes.consoleOutput.scrollTop = nodes.consoleOutput.scrollHeight;
    }

    // ---------------------------------------------------------
    // Log Panel Height Toggler
    // ---------------------------------------------------------
    nodes.consoleTrigger.addEventListener("click", (e) => {
        // Prevent toggling when clicking action buttons
        if (e.target.id === "btn-close-console") return;
        
        if (nodes.logConsole.classList.contains("collapsed")) {
            nodes.logConsole.className = nodes.btnRunPipeline.disabled 
                ? "log-console-panel expanded active" 
                : "log-console-panel expanded";
        } else {
            nodes.logConsole.className = nodes.btnRunPipeline.disabled 
                ? "log-console-panel collapsed active" 
                : "log-console-panel collapsed";
        }
    });

    nodes.btnCloseConsole.addEventListener("click", () => {
        nodes.logConsole.className = nodes.btnRunPipeline.disabled 
            ? "log-console-panel collapsed active" 
            : "log-console-panel collapsed";
    });

    // ---------------------------------------------------------
    // Master System Reset & Reseed Trigger
    // ---------------------------------------------------------
    nodes.btnResetDb.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to purge and reseed the entire database nodes? All discovered items will be reset.")) return;
        
        try {
            updateStatus("syncing", "DB_RESET");
            
            const adminKey = document.querySelector('meta[name="admin-key"]')?.content || "";
            const headers  = { "Content-Type": "application/json" };
            if (adminKey) {
                headers["x-admin-key"] = adminKey;
            }

            const response = await fetch("/api/pipeline/reset", {
                method: "POST",
                headers: headers
            });
            
            if (!response.ok) throw new Error("HTTP reset operation faulted");
            
            const data = await response.json();
            showToast("Database nodes reseeded successfully");
            
            // Purge UI filter states and refresh
            activeTrack = "all";
            activeSearch = "";
            nodes.searchInput.value = "";
            nodes.btnClearSearch.style.display = "none";
            
            await syncSystem();
        } catch (error) {
            console.error("[-] DB Reset failed:", error);
            showToast("Failed to reset database", "error");
            await syncSystem();
        }
    });

    // ---------------------------------------------------------
    // Application Initialization
    // ---------------------------------------------------------
    syncSystem();
});
