// static/chatbot.js

document.addEventListener("DOMContentLoaded", () => {
  // —— DOM references ——  
  const messageInput      = document.getElementById("message-input");
  const chatForm          = document.getElementById("chat-form");
  const messagesContainer = document.getElementById("messages-container");
  const chatList          = document.getElementById("chat-list");
  const newChatBtn        = document.getElementById("new-chat-btn");
  const deleteChatBtn     = document.getElementById("delete-chat-btn");
  const chatTitle         = document.getElementById("chat-title");
  const chatActions       = document.getElementById("chat-actions");
  const welcomeMessage    = document.getElementById("welcome-message");
  const selectedVoiceSpan = document.getElementById("selected-voice");
  
  // —— Config & state ——  
  const ASSISTANT_AVATAR_ID = window.ASSISTANT_AVATAR_ID;
  window.selectedTTSVoice   = window.selectedTTSVoice  || selectedVoiceSpan?.dataset.voice || "female_en";
  let currentChatId = null, isLoading = false;

  // —— Helpers ——  
  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendMessage(role, text) {
    const row    = document.createElement("div");
    row.className = `message-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = `message-${role}`;
    bubble.innerHTML = text;
    row.appendChild(bubble);

    messagesContainer.appendChild(row);
    scrollToBottom();

    if (role === "bot") {
      // fire-and-forget video generation
      autoGenerateVideo(text, bubble);
    }
  }

  async function autoGenerateVideo(text, bubbleContainer) {
    try {
      // 1) Generate TTS
      const fd = new FormData();
      fd.append("text", text);
      fd.append("voice", window.selectedTTSVoice);
      const ttsRes = await fetch("/generate_voice_form", { method: "POST", body: fd });
      const { audio_id } = await ttsRes.json();
      if (!audio_id) throw new Error("TTS failed");

      // 2) Generate SadTalker video
      const vidRes = await fetch(
        `/generate_video_for_chatbot/${ASSISTANT_AVATAR_ID}/${audio_id}`,
        { method: "POST" }
      );
      const { success, video_url } = await vidRes.json();
      if (!success || !video_url) throw new Error("Video gen failed");

      // 3) Inject the video under the bot bubble
      const v = document.createElement("video");
      v.src      = video_url;
      v.controls = true;
      v.autoplay = true;
      v.className= "bot-video mt-2";
      bubbleContainer.appendChild(v);
      scrollToBottom();

    } catch (e) {
      console.warn("Background video error:", e);
    }
  }

  function resetChatUI() {
    currentChatId = null;
    chatTitle.textContent = "Select a chat or start a new one";
    chatActions.classList.add("d-none");
    welcomeMessage.classList.remove("d-none");
    messagesContainer.classList.add("d-none");
    messagesContainer.innerHTML = "";
    messageInput.disabled = true;
    chatForm?.querySelector("button")?.setAttribute("disabled", "");
  }

  async function loadChat(chatId, title) {
    isLoading = true;
    currentChatId = chatId;

    chatTitle.textContent = title;
    chatActions.classList.remove("d-none");
    welcomeMessage.classList.add("d-none");
    messagesContainer.classList.remove("d-none");
    messagesContainer.innerHTML = "";

    messageInput.disabled = false;
    chatForm?.querySelector("button")?.removeAttribute("disabled");

    try {
      const res  = await fetch(`/api/chat/${chatId}/messages`);
      const data = await res.json();
      data.messages.forEach(m => {
        appendMessage("user", m.user);
        appendMessage("bot", m.bot);
      });
    } catch {
      appendMessage("bot", "Error loading chat.");
    } finally {
      isLoading = false;
      scrollToBottom();
    }
  }

  // —— Event bindings ——  

  // Send on Enter
  messageInput?.addEventListener("keydown", async e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();

      welcomeMessage.classList.add("d-none");
      messagesContainer.classList.remove("d-none");
      const msg = messageInput.value.trim();
      if (!msg || !currentChatId || isLoading) return;
      messageInput.value = "";
      appendMessage("user", msg);

      try {
        isLoading = true;
        const res  = await fetch(`/api/chat/${currentChatId}/send`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg })
        });
        const { reply } = await res.json();
        appendMessage("bot", reply);
      } catch {
        appendMessage("bot", "Error sending message.");
      } finally {
        isLoading = false;
      }
    }
  });

  // New chat
  newChatBtn?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/chat/new", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ title: "New Chat" })
      });
      const data = await res.json();
      loadChat(data.chat_id, data.title);

      // update sidebar
      const item = document.createElement("div");
      item.className         = "chat-item list-group-item list-group-item-action active";
      item.dataset.chatId    = data.chat_id;
      item.dataset.title     = data.title;
      item.innerHTML         = `<div class="d-flex w-100 justify-content-between">
                                  <h6 class="mb-1">${data.title}</h6>
                                  <small>${new Date().toLocaleTimeString()}</small>
                                </div>
                                <p class="mb-1 text-truncate">New chat started</p>`;
      chatList.prepend(item);
      document.querySelectorAll(".chat-item").forEach(i => i.classList.remove("active"));
      item.classList.add("active");
    } catch {
      appendMessage("bot", "Failed to create new chat.");
    }
  });

  // Delete chat
  deleteChatBtn?.addEventListener("click", async () => {
    if (!currentChatId || !confirm("Delete this chat?")) return;
    await fetch(`/api/chat/${currentChatId}/delete`, { method: "DELETE" });
    document.querySelector(`.chat-item[data-chat-id="${currentChatId}"]`)?.remove();
    resetChatUI();
  });

  // Sidebar load
  chatList?.addEventListener("click", e => {
    const item = e.target.closest(".chat-item");
    if (!item) return;
    loadChat(item.dataset.chatId, item.dataset.title);
    document.querySelectorAll(".chat-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
  });
});
