// 비밀번호 눈 아이콘 토글
function togglePassword(iconEl, inputEl) {
  const hidden = inputEl.getAttribute("type") === "password";
  if (hidden) {
    inputEl.setAttribute("type", "text");
    iconEl.classList.remove("fa-eye-slash");
    iconEl.classList.add("fa-eye");
  } else {
    inputEl.setAttribute("type", "password");
    iconEl.classList.remove("fa-eye");
    iconEl.classList.add("fa-eye-slash");
  }
}

// 로그인 폼/회원가입 폼 DOM
function getLoginBox() {
  return document.getElementById("login");
}
function getSignupBox() {
  return document.getElementById("signup");
}

// 로그인 폼 보여주기
function showLogin() {
  const loginBox = getLoginBox();
  const signupBox = getSignupBox();

  if (loginBox) {
    loginBox.style.display = "block";
    loginBox.classList.add("login_form_active");
  }
  if (signupBox) {
    signupBox.style.display = "none";
    signupBox.classList.remove("signup_form_active");
  }
}

// 회원가입 폼 보여주기
function showSignup() {
  const loginBox = getLoginBox();
  const signupBox = getSignupBox();

  if (signupBox) {
    signupBox.style.display = "block";
    signupBox.classList.add("signup_form_active");
  }
  if (loginBox) {
    loginBox.style.display = "none";
    loginBox.classList.remove("login_form_active");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const eyeSignup = document.getElementById("eye_icon_signup");
  const eyeLogin = document.getElementById("eye_icon_login");
  const passSignup = document.getElementById("signup_password");
  const passLogin = document.getElementById("login_password");

  // 👁 패스워드 보기/숨기기
  if (eyeSignup && passSignup) {
    eyeSignup.addEventListener("click", () => togglePassword(eyeSignup, passSignup));
  }
  if (eyeLogin && passLogin) {
    eyeLogin.addEventListener("click", () => togglePassword(eyeLogin, passLogin));
  }

  // 로그인 <-> 회원가입 전환 버튼
  const toSignup = document.getElementById("to_signup");
  const toLogin = document.getElementById("to_login");

  if (toSignup) {
    toSignup.addEventListener("click", (e) => {
      e.preventDefault();
      // 주소창 hash도 바꿔주면 새로고침 시에도 유지됨
      window.location.hash = "#signup";
      showSignup();
    });
  }

  if (toLogin) {
    toLogin.addEventListener("click", (e) => {
      e.preventDefault();
      window.location.hash = "";
      showLogin();
    });
  }

  // 첫 로드 시 어떤 폼을 보여줄지 결정
  if (window.location.hash === "#signup") {
    showSignup();
  } else {
    showLogin();
  }
});
