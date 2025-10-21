// /static/script/match_chat_script.js

// 주의: MY_USERNAME은 chat/match_chat.html의 <script> 태그에서 전역 변수로 이미 선언됨.

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

/**
 * 메시지를 채팅창에 추가하는 함수
 * @param {string} message - 메시지 내용
 * @param {string} sender - 보낸 사람 이름
 */
function displayMessage(message, sender) {
    // MY_USERNAME은 HTML 템플릿에서 Django 변수로 이미 정의됨
    const isSent = (sender === MY_USERNAME); 
    
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(isSent ? 'sent' : 'received');
    
    // 말풍선 내용 (시간, 발신자 정보 등을 추가할 수 있음)
    messageDiv.innerHTML = `
        <span class="message-content">${message}</span>
        <span class="message-sender">${sender}</span>
    `;
    
    chatBox.appendChild(messageDiv);
    chatBox.scrollTop = chatBox.scrollHeight; 
}

/**
 * 웹소켓 연결을 설정하고 이벤트 리스너를 바인딩하는 함수
 * @param {string} partnerId - 채팅방 ID (partner_id)
 */
function setupWebSocket(partnerId) {
    if (chatSocket) {
        chatSocket.close();
        chatSocket = null;
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Django Channels 라우팅에 정의된 URL 패턴과 일치해야 합니다: /ws/chat/<partner_id>/
    const socketUrl = `${protocol}//${window.location.host}/ws/chat/${partnerId}/`; 
    
    chatSocket = new WebSocket(socketUrl);

    chatSocket.onopen = function(e) {
        console.log(`WebSocket 연결 성공: ${partnerId}`);
        // 연결 성공 시, 서버에 현재 사용자 정보를 보낼 수도 있습니다.
    };

    chatSocket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        displayMessage(data.message, data.sender);
    };

    chatSocket.onclose = function(e) {
        console.log('Chat socket closed.');
    };
    
    chatSocket.onerror = function(e) {
        console.error('Chat socket error:', e);
    };
}

/**
 * 메시지 전송 처리 함수
 */
function sendMessage() {
    const message = msgInput.value.trim();
    if (message === '' || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) {
        return; 
    }
    
    chatSocket.send(JSON.stringify({
        'message': message,
        'sender': MY_USERNAME // Django 템플릿에서 받은 사용자 이름 사용
    }));
    
    msgInput.value = ''; 
}

// ===============================================
// UI 이벤트 리스너
// ===============================================

// 1. 메시지 전송 버튼 클릭 및 Enter 키 입력
sendBtn.addEventListener('click', sendMessage);

msgInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});

// 2. 파트너 목록 클릭 이벤트
matchList.addEventListener('click', (e) => {
    const card = e.target.closest('.partner-card');
    if (!card) return;

    const newPartnerId = card.dataset.roomId;
    const newPartnerName = card.querySelector('.partner-name').textContent;
    
    if (newPartnerId && newPartnerId !== currentPartnerId) {
        currentPartnerId = newPartnerId;
        
        // UI 업데이트
        document.querySelectorAll('.partner-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        partnerNameDisplay.textContent = newPartnerName;
        chatBox.innerHTML = ''; 
        
        // 웹소켓 연결 설정
        setupWebSocket(currentPartnerId);
        
        // 모바일: 채팅창 보이기
        chatArea.classList.remove('hidden');
        partnerListContainer.classList.add('hidden-mobile');
    }
});

// 3. 모바일: 목록으로 돌아가기 버튼
backToListBtn.addEventListener('click', () => {
    chatArea.classList.add('hidden');
    partnerListContainer.classList.remove('hidden-mobile');
});

// **주의**: 초기 파트너 목록 생성 코드는 Django 템플릿으로 옮겨졌으므로 여기서는 제거합니다.