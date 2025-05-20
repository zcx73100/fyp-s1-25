
// ==============================
// chatbot.js (Full Feature Version with TTS + Video + Markdown + Sidebar)
// ==============================

document.addEventListener("DOMContentLoaded", () => {
  const chatForm = document.getElementById('chat-form');
  if (!chatForm) return;
  const messageInput = document.getElementById('message-input');
  const messagesContainer = document.getElementById('messages-container');
  const welcomeMessage = document.getElementById('welcome-message');
  const chatList = document.getElementById('chat-list');
  const sidebar = document.getElementById('sidebar-wrapper');
  const toggleBtn = document.getElementById('toggle-sidebar');
  const newChatBtn = document.getElementById('new-chat-btn');
  const deleteChatBtn = document.getElementById('delete-chat-btn');
  const chatTitle = document.getElementById('chat-title');
  const chatActions = document.getElementById('chat-actions');
  const chatSearch = document.getElementById('chat-search');
  const videoOutputArea = document.getElementById("video-output-area");

  let currentChatId = null;
  let isLoading = false;
  let currentUtterance = null;
  let isTTSEnabled = true;
  let speechRate = 1.1;

  const speechSynthesis = window.speechSynthesis;

  // Sidebar toggle
  const sidebarCollapsed = localStorage.getItem("sidebarCollapsed") === "true";
  if (sidebarCollapsed) {
    sidebar.classList.add("collapsed");
    toggleBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    toggleBtn.classList.add("collapsed");
  }

  toggleBtn.addEventListener("click", () => {
    const isCollapsed = sidebar.classList.toggle("collapsed");
    localStorage.setItem("sidebarCollapsed", isCollapsed);
    toggleBtn.innerHTML = isCollapsed ? '<i class="fas fa-chevron-right"></i>' : '<i class="fas fa-chevron-left"></i>';
    toggleBtn.classList.toggle("collapsed", isCollapsed);
  });

  newChatBtn?.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/chat/new", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Chat" })
      });
      const data = await res.json();
      loadChat(data.chat_id, data.title);
      const item = document.createElement("div");
      item.className = "chat-item list-group-item list-group-item-action active";
      item.dataset.chatId = data.chat_id;
      item.dataset.title = data.title;
      item.innerHTML = `<div class="d-flex w-100 justify-content-between">
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

  deleteChatBtn?.addEventListener("click", async () => {
    if (!currentChatId || !confirm("Are you sure you want to delete this chat?")) return;
    try {
      const res = await fetch(`/api/chat/${currentChatId}/delete`, { method: "DELETE" });
      if (res.status === 204) {
        document.querySelector(`.chat-item[data-chat-id="${currentChatId}"]`)?.remove();
        resetChatUI();
      }
    } catch {
      alert("Failed to delete chat.");
    }
  });

  chatSearch?.addEventListener("input", () => {
    const query = chatSearch.value.toLowerCase();
    document.querySelectorAll(".chat-item").forEach(item => {
      const title = item.dataset.title.toLowerCase();
      item.style.display = title.includes(query) ? "" : "none";
    });
  });

  async function loadChat(chatId, title) {
    try {
      isLoading = true;
      currentChatId = chatId;
      chatTitle.textContent = title;
      chatActions.classList.remove("d-none");
      welcomeMessage.classList.add("d-none");
      messagesContainer.classList.remove("d-none");
      messageInput.disabled = false;
      chatForm.querySelector("button").disabled = false;
      messagesContainer.innerHTML = "";

      const res = await fetch(`/api/chat/${chatId}/messages`);
      const data = await res.json();
      for (const msg of data.messages) {
        appendMessage("user", msg.user);
        appendMessage("bot", msg.bot);
      }

      if (window.MathJax) MathJax.typesetPromise([messagesContainer]);
    } catch {
      appendMessage("bot", "Error loading chat.");
    } finally {
      isLoading = false;
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
    chatForm.querySelector("button").disabled = true;
  }

  function processMarkdownBold(text) {
    return text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  }

  function appendMessage(sender, message) {
    const row = document.createElement("div");
    row.className = `message-row ${sender}`;
    const div = document.createElement("div");
    div.className = `message-${sender}`;
    const processed = processMarkdownBold(message);
    div.innerHTML = `<div>${processed}</div>`;
    row.appendChild(div);

    if (sender === "bot") {
      const controls = document.createElement("div");
      controls.className = "tts-controls";
      controls.innerHTML = `
        <button class="tts-btn"><i class="fas fa-volume-up"></i> Read</button>
        <button class="tts-stop-btn"><i class="fas fa-stop"></i> Stop</button>
      `;
      div.appendChild(controls);
      controls.querySelector(".tts-btn").addEventListener("click", () => speakText(message));
      controls.querySelector(".tts-stop-btn").addEventListener("click", stopSpeech);
    }

    messagesContainer.appendChild(row);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  chatForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (!message || !currentChatId || isLoading) return;
    appendMessage("user", message);
    messageInput.value = "";

    try {
      isLoading = true;
      const res = await fetch(`/api/chat/${currentChatId}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      });
      const data = await res.json();
      appendMessage("bot", data.reply);
      await autoGenerateVideo(data.reply);
    } catch {
      appendMessage("bot", "Sorry, something went wrong.");
    } finally {
      isLoading = false;
    }
  });

  chatList?.addEventListener("click", (e) => {
    const item = e.target.closest(".chat-item");
    if (!item) return;
    document.querySelectorAll(".chat-item").forEach(i => i.classList.remove("active"));
    item.classList.add("active");
    loadChat(item.dataset.chatId, item.dataset.title);
  });

  let originalTitle = "";
  chatTitle?.addEventListener("focus", () => {
    originalTitle = chatTitle.textContent.trim();
  });
  chatTitle?.addEventListener("blur", async () => {
    const newTitle = chatTitle.textContent.trim();
    if (!currentChatId || newTitle === "" || newTitle === originalTitle) return;
    try {
      await fetch(`/api/chat/${currentChatId}/update_title`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle })
      });
      const sidebarItem = document.querySelector(`.chat-item[data-chat-id="${currentChatId}"]`);
      if (sidebarItem) {
        sidebarItem.querySelector("h6").textContent = newTitle;
        sidebarItem.dataset.title = newTitle;
      }
    } catch {
      chatTitle.textContent = originalTitle;
    }
  });
  chatTitle?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      chatTitle.blur();
    }
  });

  function stopSpeech() {
    speechSynthesis.cancel();
  }

  async function speakText(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = speechRate;
    utterance.pitch = 1.2;
    utterance.volume = 1.0;

    const voices = speechSynthesis.getVoices();
    const preferred = voices.find(v => v.lang.startsWith("en")) || voices[0];
    utterance.voice = preferred;

    speechSynthesis.speak(utterance);
  }

  async function autoGenerateVideo(text) {
  try {
    const formData = new FormData();
    formData.append("text", text);

    const voice = window.selectedTTSVoice || "female_en";
    const lang = voice.includes("jp") ? "ja" :
                 voice.includes("id") ? "id" :
                 voice.includes("es") ? "es" :
                 voice.includes("fr") ? "fr" :
                 voice.includes("de") ? "de" :
                 voice.includes("it") ? "it" : "en";
    const gender = voice.includes("female") ? "female" : "male";

    formData.append("lang", lang);
    formData.append("gender", gender);
    formData.append("source", "chatbot")
    const voiceRes = await fetch("/generate_voice_form", {
      method: "POST",
      body: formData
    });

    const { audio_id } = await voiceRes.json();
    if (!audio_id) return;

    const videoRes = await fetch(`/generate_video_for_chatbot/${window.ASSISTANT_AVATAR_ID}/${audio_id}`, {
      method: "POST"
    });

    const { success, task_id } = await videoRes.json();
    if (success && task_id) {
      checkAndReplaceAvatarWithVideo(task_id); // ✅ This is what swaps avatar → video
    } else {
      console.warn("❌ Video generation failed.");
    }
  } catch (err) {
    console.error("Error during autoGenerateVideo:", err);
  }
}

  // This function checks if video is ready and updates the avatar accordingly
async function checkAndReplaceAvatarWithVideo(taskId) {
  try {
    const checkUrl = `/check_video/${taskId}`;
    let attempts = 0;

    const intervalId = setInterval(async () => {
      const res = await fetch(checkUrl);
      const data = await res.json();

      if (data.ready) {
        clearInterval(intervalId);

        if (data.error) {
          console.error("❌ Video generation failed:", data.error);
          return;
        }

        const videoUrl = `/stream_video/${data.video_id}`;
        const avatarWrapper = document.getElementById("assistant-header");
        if (!avatarWrapper) {
          console.warn("⚠️ Could not find #assistant-header.");
          return;
        }

        avatarWrapper.innerHTML = `
          <video id="assistant-video" class="rounded-circle shadow-sm" style="max-width: 150px;" autoplay loop muted>
            <source src="${videoUrl}" type="video/mp4" />
            Your browser does not support the video tag.
          </video>
        `;
        console.log("✅ Persistent avatar replaced with video:", videoUrl);
      }

      if (++attempts >= 60) {
        clearInterval(intervalId);
        console.warn("⏱️ Video not ready after waiting.");
      }
    }, 1000);
  } catch (err) {
    console.error("Error polling for video:", err);
  }
}

});
