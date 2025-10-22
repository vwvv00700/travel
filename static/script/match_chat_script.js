const matchList = document.getElementById('match-list');
const chatBox = document.getElementById('chat-box');
const msgInput = document.getElementById('msg-input');
const sendBtn = document.getElementById('send-btn');
const partnerNameDisplay = document.getElementById('partner-name');
const chatArea = document.getElementById('chat-area');
const partnerListContainer = document.getElementById('sidebar');
const backToListBtn = document.getElementById('back-to-list-btn');

let chatSocket = null;
let currentPartnerId = null;

function displayMessage(message, sender) {
    const isSent = sender === MY_USERNAME; 
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(isSent ? 'sent' : 'received');
    messageDiv.innerHTML = `<span class="message-content">${message}</span><span class="message-sender">${sender}</span>`;
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight; 
}

function setupWebSocket(partnerId) {
    if (chatSocket) chatSocket.close();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    chatSocket = new WebSocket(`${protocol}//${window.location.host}/ws/chat/${partnerId}/`);

    chatSocket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        displayMessage(data.message, data.sender);
    };

    chatSocket.onopen = function() { console.log(`Connected to ${partnerId}`); };
    chatSocket.onclose = function() { console.log('Socket closed'); };
}

function sendMessage() {
    const message = msgInput.value.trim();
    if (!message || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) return;
    chatSocket.send(JSON.stringify({'message': message, 'sender': MY_USERNAME}));
    msgInput.value = '';
}

sendBtn.addEventListener('click', sendMessage);
msgInput.addEventListener('keypress', (e) => { if(e.key==='Enter') sendMessage(); });

matchList.addEventListener('click', (e) => {
    const card = e.target.closest('.partner-card');
    if (!card) return;
    const newPartnerId = card.dataset.roomId;
    const newPartnerName = card.querySelector('.partner-name').textContent;
    if (newPartnerId !== currentPartnerId) {
        currentPartnerId = newPartnerId;
        document.querySelectorAll('.partner-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        partnerNameDisplay.textContent = newPartnerName;
        chatBox.innerHTML = '';
        setupWebSocket(currentPartnerId);
        chatArea.classList.remove('hidden');
        partnerListContainer.classList.add('hidden-mobile');
    }
});

backToListBtn.addEventListener('click', () => {
    chatArea.classList.add('hidden');
    partnerListContainer.classList.remove('hidden-mobile');
});