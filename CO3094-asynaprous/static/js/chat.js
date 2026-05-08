// P2P Chat Frontend Logic

let lastMessageCount = 0;
let cachedPeers = {};

function jsonFetch(url, options = {}) {
  return fetch(url, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  }).then((response) => response.json());
}

function getValue(id, fallback = '') {
  const element = document.getElementById(id);
  return element ? element.value.trim() : fallback;
}

function updateChatWindow(messages) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return;

  chatWindow.innerHTML = '';
  messages.forEach((msg) => {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${msg.direction || ''}`;
    const time = msg.timestamp ? new Date(msg.timestamp * 1000).toLocaleTimeString() : '';
    msgDiv.textContent = `[${time}] ${msg.channel || 'general'} | ${msg.sender}: ${msg.message}`;
    chatWindow.appendChild(msgDiv);
  });
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showNotification() {
  const notification = document.getElementById('notification');
  if (!notification) return;
  notification.style.display = 'block';
  setTimeout(() => { notification.style.display = 'none'; }, 3000);
}

function pollMessages() {
  jsonFetch('/poll-messages')
    .then((data) => {
      if (!data.ok) return;
      const messages = data.messages || [];
      if (messages.length > lastMessageCount) {
        updateChatWindow(messages);
        const newMessages = messages.slice(lastMessageCount);
        if (newMessages.some((msg) => msg.sender !== 'Me')) showNotification();
        lastMessageCount = messages.length;
      }
    })
    .catch((error) => console.error('Error polling messages:', error));
}

function refreshPeers() {
  return jsonFetch('/get-list', { method: 'GET' })
    .then((data) => {
      if (!data.ok) {
        console.warn('get-list failed:', data.message);
        return data;
      }
      cachedPeers = data.peers || {};
      const peerSelect = document.getElementById('peer-select');
      if (peerSelect) {
        peerSelect.innerHTML = '';
        Object.entries(cachedPeers).forEach(([peerId, peer]) => {
          const option = document.createElement('option');
          option.value = peerId;
          option.textContent = `${peerId} (${peer.ip}:${peer.port})`;
          peerSelect.appendChild(option);
        });
      }
      return data;
    })
    .catch((error) => console.error('Error refreshing peers:', error));
}

function registerPeer() {
  const peerId = getValue('peer-id');
  const ip = getValue('peer-ip', '127.0.0.1');
  const port = getValue('peer-port');
  const channel = getValue('channel', 'general');
  if (!peerId || !ip || !port) {
    alert('Please fill peer id, ip, and port');
    return;
  }

  jsonFetch('/submit-info', {
    method: 'POST',
    body: JSON.stringify({ peer_id: peerId, ip, port })
  })
    .then((data) => {
      if (!data.ok) {
        alert(data.message || 'Register failed');
        return data;
      }
      return jsonFetch('/add-list', {
        method: 'POST',
        body: JSON.stringify({ peer_id: peerId, channel })
      });
    })
    .then(() => refreshPeers())
    .catch((error) => console.error('Error registering peer:', error));
}

function sendMessage() {
  const selectedPeerId = getValue('peer-select');
  const selectedPeer = cachedPeers[selectedPeerId];
  const targetIp = selectedPeer ? selectedPeer.ip : getValue('target-ip');
  const targetPort = selectedPeer ? selectedPeer.port : getValue('target-port');
  const message = getValue('message-input');
  const channel = getValue('channel', 'general');

  if (!targetIp || !targetPort || !message) {
    alert('Please fill target IP, port, and message');
    return;
  }

  jsonFetch('/send-peer', {
    method: 'POST',
    body: JSON.stringify({
      target_ip: targetIp,
      target_port: targetPort,
      message,
      channel
    })
  })
    .then((data) => {
      if (data.ok) {
        const input = document.getElementById('message-input');
        if (input) input.value = '';
        setTimeout(pollMessages, 300);
      } else {
        alert('Failed to send message: ' + data.message);
      }
    })
    .catch((error) => console.error('Error sending message:', error));
}

function broadcastMessage() {
  const message = getValue('message-input');
  const peerId = getValue('peer-id');
  const channel = getValue('channel', 'general');
  if (!message) {
    alert('Please enter a message');
    return;
  }

  refreshPeers().then(() => {
    const peers = Object.entries(cachedPeers)
      .filter(([id]) => id !== peerId)
      .map(([, peer]) => ({ ip: peer.ip, port: peer.port }));

    jsonFetch('/broadcast-peer', {
      method: 'POST',
      body: JSON.stringify({ peer_id: peerId, message, channel, peers })
    })
      .then((data) => {
        if (data.ok) {
          const input = document.getElementById('message-input');
          if (input) input.value = '';
          setTimeout(pollMessages, 300);
        } else {
          alert('Broadcast failed: ' + data.message);
        }
      })
      .catch((error) => console.error('Error broadcasting message:', error));
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const registerButton = document.getElementById('register-button');
  const refreshButton = document.getElementById('refresh-button');
  const sendButton = document.getElementById('send-button');
  const broadcastButton = document.getElementById('broadcast-button');

  if (registerButton) registerButton.addEventListener('click', registerPeer);
  if (refreshButton) refreshButton.addEventListener('click', refreshPeers);
  if (sendButton) sendButton.addEventListener('click', sendMessage);
  if (broadcastButton) broadcastButton.addEventListener('click', broadcastMessage);

  refreshPeers();
  pollMessages();
  setInterval(refreshPeers, 5000);
  setInterval(pollMessages, 2000);
});
