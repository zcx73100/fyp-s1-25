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

  function sendOnEnter(event) {
    if (event.key === 'Enter') {
      const input = document.getElementById('chat-input');
      const message = input.value.trim();
      if (!message) return;
      appendMessage('You', message, 'user');
      input.value = '';
  
      const status = document.getElementById('status');
      let dotCount = 0;
      status.innerText = 'AI is typing';
      typingInterval = setInterval(() => {
        dotCount = (dotCount + 1) % 4;
        status.innerText = 'AI is typing' + '.'.repeat(dotCount);
      }, 500);
  
      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message })
      })
        .then(res => res.json())
        .then(data => {
          clearInterval(typingInterval);
          status.innerText = '';
          appendMessage('AI', data.reply || 'Sorry, no reply.', 'bot');
        })
        .catch(() => {
          clearInterval(typingInterval);
          status.innerText = '';
          appendMessage('AI', 'Error connecting.', 'bot');
        });
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
  