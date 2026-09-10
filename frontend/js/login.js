// ========================
// LOGIN PAGE JS
// ========================

function togglePassword() {
  const pwd = document.getElementById('password');
  pwd.type = pwd.type === 'password' ? 'text' : 'password';
}

async function handleLogin(e) {
  e.preventDefault();
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const btn = document.querySelector('.btn-signin');

  if (!username || !password) {
    showLoginError('Please enter username and password');
    return;
  }

  btn.innerHTML = '<span class="btn-text">Signing In...</span><div class="btn-glow"></div>';
  btn.disabled = true;

  try {
    const res = await fetch('http://localhost:5000/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (data.success) {
      localStorage.setItem('cognisense_user', JSON.stringify({ username: data.username, id: data.user_id }));
      btn.innerHTML = '<span class="btn-text">✓ Authenticated</span><div class="btn-glow"></div>';
      setTimeout(() => { window.location.href = 'pages/dashboard.html'; }, 600);
    } else {
      showLoginError(data.message || 'Invalid credentials');
      btn.innerHTML = '<span class="btn-text">Sign In</span><div class="btn-glow"></div>';
      btn.disabled = false;
    }
  } catch (err) {
    // Demo mode — allow login without backend
    localStorage.setItem('cognisense_user', JSON.stringify({ username: username || 'Shrushti', id: 1 }));
    btn.innerHTML = '<span class="btn-text">✓ Demo Mode</span><div class="btn-glow"></div>';
    setTimeout(() => { window.location.href = 'pages/dashboard.html'; }, 600);
  }
}

function handleCreateAccount() {
  const card = document.querySelector('.login-card');
  card.style.transform = 'scale(0.97)';
  card.style.opacity = '0.7';
  setTimeout(() => {
    card.style.transform = '';
    card.style.opacity = '';
    alert('Account registration coming soon!');
  }, 200);
}

function showLoginError(msg) {
  let err = document.querySelector('.login-error');
  if (!err) {
    err = document.createElement('p');
    err.className = 'login-error';
    err.style.cssText = 'color:#ef4444;font-size:13px;text-align:center;margin-top:10px;animation:fadeIn 0.3s;';
    document.querySelector('.login-form').appendChild(err);
  }
  err.textContent = msg;
  setTimeout(() => err.remove(), 3000);
}

// Animate card on load
window.addEventListener('DOMContentLoaded', () => {
  const card = document.querySelector('.login-card');
  card.style.opacity = '0';
  card.style.transform = 'translateY(30px)';
  requestAnimationFrame(() => {
    card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    card.style.opacity = '1';
    card.style.transform = 'translateY(0)';
  });

  const heroText = document.querySelector('.login-hero-text');
  if (heroText) {
    heroText.style.opacity = '0';
    heroText.style.transform = 'translateY(20px)';
    setTimeout(() => {
      heroText.style.transition = 'opacity 0.8s ease 0.3s, transform 0.8s ease 0.3s';
      heroText.style.opacity = '1';
      heroText.style.transform = 'translateY(0)';
    }, 100);
  }
});