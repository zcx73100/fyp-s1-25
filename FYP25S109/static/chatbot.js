// Toggle the chat window open/closed
function toggleChat() {
  const chatBox   = document.getElementById('chat-box');
  const container = document.getElementById('chatbot-container');
  const isOpen    = chatBox.style.display === 'flex';

  if (isOpen) {
    // Minimize
    chatBox.style.display = 'none';
    container.classList.remove('expanded');
    container.style.width  = '200px';
    container.style.height = 'auto';
  } else {
    // Open
    chatBox.style.display = 'flex';
    container.style.width  = container.classList.contains('expanded') ? '450px' : '300px';
    container.style.height = container.classList.contains('expanded') ? '600px' : '400px';
  }
}

// Expand/collapse between two sizes
function toggleSize() {
  const container = document.getElementById('chatbot-container');
  const chatBox   = document.getElementById('chat-box');
  const expandBtn = document.getElementById('expand-button');

  container.classList.toggle('expanded');
  const isExpanded = container.classList.contains('expanded');

  container.style.width  = isExpanded ? '450px' : '300px';
  container.style.height = isExpanded ? '600px' : '400px';
  expandBtn.innerText    = isExpanded ? '🗕 Collapse' : '🗖 Expand';

  if (chatBox.style.display === 'none') {
    chatBox.style.display = 'flex';
  }
}

// Create a chat bubble element
function createChatBubble(role, text) {
  const bubble = document.createElement('div');
  bubble.className = `chat-bubble ${role}-bubble`;
  bubble.innerHTML = text;
  return bubble;
}

let typingInterval;

// Handle Enter in the chat input
async function sendOnEnter(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();

    const input    = e.target;
    const message  = input.value.trim();
    if (!message) return;

    input.value = "";

    const chatBox = document.getElementById("chat-box");
    const userBubble = createChatBubble("user", message);
    chatBox.appendChild(userBubble);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
      // 1. Send the message to your API
      const chatId = input.getAttribute("data-chat-id");
      const res = await fetch(`/api/chat/${chatId}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Chat failed");

      // 2. Render the bot’s reply
      const reply = data.reply;
      const botBubble = createChatBubble("bot", reply);
      chatBox.appendChild(botBubble);
      chatBox.scrollTop = chatBox.scrollHeight;

      // 3. Stash the reply for TTS
      document.getElementById("hidden-reply-text").value = reply;

      // 4. Build FormData for voice generation
      const formData = new FormData();
      formData.append("text", reply);

      const selectedVoice = document.querySelector("#voice-selector").value || "female_en";
      const lang   = selectedVoice.includes("jp")     ? "ja"     : "en";
      const gender = selectedVoice.includes("female") ? "female" : "male";
      formData.append("lang", lang);
      formData.append("gender", gender);

      // 5. Call your form-based TTS endpoint
      const ttsRes  = await fetch("/generate_voice_form", {
        method: "POST",
        body: formData
      });
      const ttsData = await ttsRes.json();
      if (ttsRes.ok && ttsData.audio_id) {
        console.log("🎤 Voice generated, audioId:", ttsData.audio_id);
        // 6. Kick off the SadTalker video build
        await triggerSadTalkerVideo(ttsData.audio_id);
      } else {
        console.error("❌ TTS failed:", ttsData.error || "no audio_id");
        showNotification(ttsData.error || "Voice generation failed", "danger");
      }

    } catch (err) {
      console.error("❌ Chatbot error:", err);
      showNotification(err.message || "Something went wrong", "danger");
    }
  }
}

// Utility to show notifications (implement UI as you like)
function showNotification(msg, type) {
  // e.g. insert into a toast container, styled by `type`
  console.warn(`[${type.toUpperCase()}] ${msg}`);
}

// Stub for SadTalker video trigger (fill in your logic)
async function triggerSadTalkerVideo(audioId) {
  // your existing code here
}

// Wire up the Enter key handler
document.getElementById("chat-input")
        .addEventListener("keydown", sendOnEnter);

// (Optional) Generic appendMessage if you need it elsewhere
function appendMessage(sender, text, role) {
  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'bot-bubble'}`;
  msgDiv.innerHTML = `<strong>${sender}:</strong><br>${text}`;
  const chat = document.getElementById('chat-messages');
  chat.appendChild(msgDiv);
  msgDiv.scrollIntoView();
}
