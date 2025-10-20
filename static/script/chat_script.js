let ws;

fetch("/api/matches")
.then(res => res.json())
.then(data => {
    const container = document.getElementById("match-cards");
    container.innerHTML = "";
    data.forEach(user => {
        const card = document.createElement("div");
        card.className = "card";

        const name = document.createElement("h2");
        name.innerText = user.name;
        card.appendChild(name);

        const intro = document.createElement("p");
        intro.innerText = user.intro;
        card.appendChild(intro);

        user.badges.forEach(b => {
            const badge = document.createElement("span");
            badge.className = "badge";
            badge.innerText = b;
            card.appendChild(badge);
        });

        container.appendChild(card);
    });

    // WebSocket 자동 연결
    data.forEach(user => {
        ws = new WebSocket(`ws://${window.location.host}/ws/${user.user_id}`);
        ws.onmessage = (event) => {
            const chatBox = document.getElementById("chat-box");
            chatBox.innerHTML += `<div>${event.data}</div>`;
            chatBox.scrollTop = chatBox.scrollHeight;
        };
    });
});

// 채팅 전송
document.getElementById("send-btn").onclick = () => {
    const msgInput = document.getElementById("msg-input");
    if (!ws) { alert("웹소켓 연결 안됨"); return; }
    ws.send(msgInput.value);
    msgInput.value = "";
};