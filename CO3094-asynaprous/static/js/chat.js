// chat.js - P2P Chat Frontend Logic

let lastMessageCount = 0;

function pollMessages() {
    fetch('/poll-messages', {
        credentials: 'include'
    })
        .then(response => response.json())
        .then(data => {
            if (data.ok) {
                const messages = data.messages;
                if (messages.length > lastMessageCount) {
                    updateChatWindow(messages);
                    // Only show notification if new messages are from other users
                    const newMessages = messages.slice(lastMessageCount);
                    if (newMessages.some(msg => msg.sender !== "Me")) {
                        showNotification();
                    }
                    lastMessageCount = messages.length;
                }
            }
        })
        .catch(error => console.error('Error polling messages:', error));
}

function updateChatWindow(messages) {
    const chatWindow = document.getElementById('chat-window');
    chatWindow.innerHTML = '';
    messages.forEach(msg => {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message';
        msgDiv.innerHTML = `<strong>${msg.sender}:</strong> ${msg.message}`;
        chatWindow.appendChild(msgDiv);
    });
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showNotification() {
    const notification = document.getElementById('notification');
    notification.style.display = 'block';
    setTimeout(() => {
        notification.style.display = 'none';
    }, 3000);
}

function sendMessage() {
    const targetIp = document.getElementById('target-ip').value;
    const targetPort = document.getElementById('target-port').value;
    const message = document.getElementById('message-input').value;

    if (!targetIp || !targetPort || !message) {
        alert('Please fill in target IP, port, and message');
        return;
    }

    fetch('/send-peer', {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            target_ip: targetIp,
            target_port: targetPort,
            message: message
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.ok) {
            document.getElementById('message-input').value = '';
        } else {
            alert('Failed to send message: ' + data.message);
        }
    })
    .catch(error => console.error('Error sending message:', error));
}

function broadcastMessage() {
    const message = document.getElementById('message-input').value;
    if (!message) {
        alert('Please enter a message');
        return;
    }

    // Hardcoded peers for broadcast
    const peers = [
        { ip: '127.0.0.1', port: '8081' },
        { ip: '127.0.0.1', port: '8082' }
    ];

    fetch('/broadcast-peer', {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            peers: peers,
            message: message
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.ok) {
            document.getElementById('message-input').value = '';
            console.log('Broadcast results:', data.results);
        } else {
            alert('Failed to broadcast: ' + data.message);
        }
    })
    .catch(error => console.error('Error broadcasting:', error));
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('send-button').addEventListener('click', sendMessage);
    document.getElementById('broadcast-button').addEventListener('click', broadcastMessage);

    // Start polling
    setInterval(pollMessages, 2000);
    pollMessages(); // Initial poll
});