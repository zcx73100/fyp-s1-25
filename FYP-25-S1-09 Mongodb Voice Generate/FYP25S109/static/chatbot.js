function toggleChat() {
    const chatBox = document.getElementById('chat-box');
    const container = document.getElementById('chatbot-container');
    const isOpen = chatBox.style.display === 'flex';
  
    if (isOpen) {
      // Minimize
      chatBox.style.display = 'none';
      container.classList.remove('expanded'); 
      container.style.width = '200px';
      container.style.height = 'auto';
    } else {
      // Open
      chatBox.style.display = 'flex';
      container.style.width = container.classList.contains('expanded') ? '450px' : '300px';
      container.style.height = container.classList.contains('expanded') ? '600px' : '400px';
    }
  }
  
  function toggleSize() {
    const container = document.getElementById('chatbot-container');
    const chatBox = document.getElementById('chat-box');
    const expandBtn = document.getElementById('expand-button');
  
    container.classList.toggle('expanded');
  
    const isExpanded = container.classList.contains('expanded');
  
    container.style.height = isExpanded ? '600px' : '400px';
    container.style.width = isExpanded ? '450px' : '300px';
    expandBtn.innerText = isExpanded ? '🗕 Collapse' : '🗖 Expand';
  
    if (chatBox.style.display === 'none') {
      chatBox.style.display = 'flex';
    }
  }

    let typingInterval;

    async function sendOnEnter(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const input = e.target;
        const message = input.value.trim();
        if (!message) return;

        input.value = "";

        const chatBox = document.getElementById("chat-box");
        const userBubble = createChatBubble("user", message);
        chatBox.appendChild(userBubble);
        chatBox.scrollTop = chatBox.scrollHeight;

        try {
          const chatId = input.getAttribute("data-chat-id");
          const res = await fetch(`/api/chat/${chatId}/send`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message })
          });

          const data = await res.json();
          const reply = data.reply;
          if (!reply) throw new Error("No reply");

          const botBubble = createChatBubble("bot", reply);
          chatBox.appendChild(botBubble);
          chatBox.scrollTop = chatBox.scrollHeight;

          // ✅ Now submit reply to backend to generate voice & video
          document.getElementById("hidden-reply-text").value = reply;
          //document.getElementById("voice-form").submit();

          const replyText = document.getElementById("hidden-reply-text").value;
          const formData = new FormData();
          formData.append("text", replyText);
          // ✅ Dynamically capture selected voice
          const selectedVoice = document.querySelector("#voice-selector").value || "female_en";
          const lang = selectedVoice.includes("jp") ? "ja" : "en";
          const gender = selectedVoice.includes("female") ? "female" : "male";

          formData.append("lang", lang);
          formData.append("gender", gender);

          try {
            const res = await fetch("/generate_voice_form", {
              method: "POST",
              body: formData
            });

            const data = await res.json();
            const audioId = data.audio_id;

            if (audioId) {
              console.log("🎤 Voice generated, audioId:", audioId);
              await triggerSadTalkerVideo(audioId);
            } else {
              console.error("❌ Failed to get audio ID");
            }
          } catch (err) {
            console.error("❌ Error generating voice:", err);
          }

        } catch (err) {
          console.error("❌ Chatbot error:", err);
        }
      }
    }


  function appendMessage(sender, text, role) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-bubble ${role === 'user' ? 'user-bubble' : 'bot-bubble'}`;
    msgDiv.innerHTML = `<strong>${sender}:</strong><br>${text}`;
    const chat = document.getElementById('chat-messages');
    chat.appendChild(msgDiv);
    msgDiv.scrollIntoView();
  }
