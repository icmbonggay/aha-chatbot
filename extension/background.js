// AHA browser extension: adds "Explain like I'm five" to the right-click
// menu for highlighted text, sends the text to the local Python server,
// and shows the answer in a bubble next to the selection.

const SERVER_URL = "http://127.0.0.1:8765/explain";
const MENU_ID = "aha-eli5";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Explain \"%s\" like I'm five",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !tab?.id) return;

  const tabId = tab.id;
  // frameId keeps the bubble in the same frame as the selection (iframes).
  const target = { tabId, frameIds: [info.frameId ?? 0] };

  const shown = await showBubble(target, "loading", "Thinking...");
  if (!shown) return; // Chrome blocks scripts on pages like chrome:// and the Web Store.

  const { state, text } = await explain(info.selectionText);
  await showBubble(target, state, text);
});

async function explain(selection) {
  try {
    const response = await fetch(SERVER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: selection }),
    });
    const body = await response.json();
    if (!response.ok) return { state: "error", text: body.error || "Something went wrong." };
    return { state: "done", text: body.explanation };
  } catch (e) {
    return {
      state: "error",
      text: "Can't reach AHA. Start it with: python src/explain_server.py",
    };
  }
}

async function showBubble(target, state, text) {
  try {
    await chrome.scripting.executeScript({ target, func: renderBubble, args: [state, text] });
    return true;
  } catch (e) {
    console.warn("AHA can't show a bubble on this page:", e.message);
    return false;
  }
}

// Runs inside the web page, so it can't use anything from this file.
// Chrome copies the function's source into the page.
function renderBubble(state, text) {
  const HOST_ID = "aha-eli5-bubble";
  let host = document.getElementById(HOST_ID);

  // A new question replaces the old bubble so it opens next to the new selection.
  if (host && state === "loading") {
    host.ahaClose?.();
    host = null;
  }

  if (!host) {
    host = document.createElement("div");
    host.id = HOST_ID;
    // A shadow root keeps the page's CSS from restyling the bubble, and ours from leaking out.
    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        .bubble {
          position: fixed; z-index: 2147483647; width: 360px; max-height: 60vh;
          overflow-y: auto; box-sizing: border-box; padding: 14px 16px 16px;
          background: #fffdf7; color: #1f1d1a; border: 1px solid #e6dfcf;
          border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,.18);
          font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .head { display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 8px; font-weight: 600; font-size: 13px; color: #8a5a00; }
        .close { border: 0; background: none; font-size: 18px; line-height: 1;
                 cursor: pointer; color: #8b857a; padding: 0 2px; }
        .close:hover { color: #1f1d1a; }
        .body { white-space: pre-wrap; margin: 0; }
        .loading .body { color: #8b857a; font-style: italic; }
        .error .body { color: #b42318; }
        @media (prefers-color-scheme: dark) {
          .bubble { background: #22201c; color: #f2efe8; border-color: #3a362f; }
          .head { color: #f0b54a; }
          .close:hover { color: #f2efe8; }
          .error .body { color: #ff8a80; }
        }
      </style>
      <div class="bubble" role="dialog" aria-label="AHA explanation">
        <div class="head"><span>AHA, like you're five</span>
          <button class="close" aria-label="Close">&times;</button></div>
        <p class="body"></p>
      </div>`;
    document.documentElement.appendChild(host);

    const close = () => {
      host.remove();
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("mousedown", onClickOutside, true);
    };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    const onClickOutside = (e) => { if (!e.composedPath().includes(host)) close(); };
    host.ahaClose = close;
    root.querySelector(".close").addEventListener("click", close);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("mousedown", onClickOutside, true);

    // Place it under the selection, kept inside the window.
    const bubble = root.querySelector(".bubble");
    const selection = window.getSelection();
    const rect = selection && selection.rangeCount
      ? selection.getRangeAt(0).getBoundingClientRect()
      : null;
    const margin = 12;
    const width = Math.min(360, window.innerWidth - margin * 2);
    bubble.style.width = width + "px";
    let left = rect ? rect.left : window.innerWidth - width - margin;
    left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));
    const top = rect ? rect.bottom + 8 : margin;
    // Near the bottom of the window, open above the selection instead.
    if (rect && top > window.innerHeight * 0.6) {
      bubble.style.bottom = (window.innerHeight - rect.top + 8) + "px";
    } else {
      bubble.style.top = top + "px";
    }
    bubble.style.left = left + "px";
  }

  const bubble = host.shadowRoot.querySelector(".bubble");
  bubble.className = "bubble " + state;
  // textContent, never innerHTML: the reply is plain text and must not run as HTML.
  // Strip markdown bold/italics markers since the bubble shows plain text.
  host.shadowRoot.querySelector(".body").textContent = text.replace(/\*\*|__/g, "");
}
