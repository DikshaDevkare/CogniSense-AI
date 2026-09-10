// ========================
// PARTICLES & NEURAL CANVAS
// ========================

(function () {
  const canvas = document.getElementById('neural-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let W, H, nodes = [], animFrame;

  function resize() {
    W = canvas.width = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }

  function createNodes(count) {
    nodes = [];
    for (let i = 0; i < count; i++) {
      nodes.push({
        x: Math.random() * W,
        y: Math.random() * H,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        r: Math.random() * 2 + 1,
        color: ['#a855f7', '#6366f1', '#0ea5e9', '#06b6d4'][Math.floor(Math.random() * 4)],
        opacity: Math.random() * 0.6 + 0.2
      });
    }
  }

  function drawNeural() {
    ctx.clearRect(0, 0, W, H);

    // Connections
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[i].x - nodes[j].x;
        const dy = nodes[i].y - nodes[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 150) {
          const alpha = (1 - dist / 150) * 0.18;
          ctx.beginPath();
          ctx.strokeStyle = `rgba(168,85,247,${alpha})`;
          ctx.lineWidth = 0.6;
          ctx.moveTo(nodes[i].x, nodes[i].y);
          ctx.lineTo(nodes[j].x, nodes[j].y);
          ctx.stroke();
        }
      }
    }

    // Nodes
    nodes.forEach(n => {
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = n.color;
      ctx.globalAlpha = n.opacity;
      ctx.fill();
      ctx.globalAlpha = 1;

      n.x += n.vx;
      n.y += n.vy;
      if (n.x < 0 || n.x > W) n.vx *= -1;
      if (n.y < 0 || n.y > H) n.vy *= -1;
    });

    animFrame = requestAnimationFrame(drawNeural);
  }

  function init() {
    resize();
    createNodes(80);
    drawNeural();
  }

  window.addEventListener('resize', () => {
    cancelAnimationFrame(animFrame);
    resize();
    createNodes(80);
    drawNeural();
  });

  init();

  // Floating particles DOM
  const container = document.getElementById('particles');
  if (container) {
    for (let i = 0; i < 30; i++) {
      const p = document.createElement('div');
      p.className = 'particle';
      const size = Math.random() * 4 + 2;
      const colors = ['rgba(168,85,247,0.6)', 'rgba(99,102,241,0.6)', 'rgba(14,165,233,0.6)', 'rgba(6,182,212,0.5)'];
      p.style.cssText = `
        width:${size}px; height:${size}px;
        background:${colors[Math.floor(Math.random() * colors.length)]};
        left:${Math.random() * 100}%;
        animation-duration:${Math.random() * 15 + 10}s;
        animation-delay:-${Math.random() * 20}s;
        box-shadow: 0 0 ${size * 3}px ${colors[Math.floor(Math.random() * colors.length)]};
      `;
      container.appendChild(p);
    }
  }
})();