"""An on-page panel showing Jev's probability across the four directions.

The panel is drawn into the page beside the board, so the video recorder
captures it along with the game. Presentation only: nothing here affects a
decision.
"""

from __future__ import annotations

PANEL_WIDTH = 300

INSTALL_OVERLAY = """
(canvas) => {
  const rect = canvas.getBoundingClientRect();
  const panel = document.createElement('div');
  panel.id = 'jev-panel';
  panel.innerHTML = '<div class="jev-bars" id="jev-bars"></div>';
  Object.assign(panel.style, {
    position: 'absolute',
    left: (window.scrollX + rect.right) + 'px',
    top: (window.scrollY + rect.top) + 'px',
    width: '%(width)spx',
    height: rect.height + 'px',
  });
  document.body.appendChild(panel);

  const style = document.createElement('style');
  style.textContent = `
    #jev-panel {
      box-sizing: border-box; padding: 0 30px; z-index: 2147483647;
      background: #16250d; color: #eaf5dc;
      font-family: 'Roboto', system-ui, sans-serif;
      display: flex; flex-direction: column; justify-content: center;
    }
    .jev-bars { display: flex; flex-direction: column; gap: 26px; }
    .jev-row { display: flex; flex-direction: column; gap: 9px; }
    .jev-line { display: flex; justify-content: space-between; align-items: baseline; }
    .jev-label {
      font-size: 15px; color: #b9d194;
      text-transform: uppercase; letter-spacing: 1.6px;
    }
    .jev-val { font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
    .jev-track { display: block; height: 14px; background: #2a3f1a; border-radius: 7px; overflow: hidden; }
    .jev-fill {
      display: block; height: 14px; width: 0%%; background: #aad751;
      border-radius: 7px; transition: width .1s linear;
    }
    .jev-fill.danger { background: #e7471d; }
  `;
  document.head.appendChild(style);

  const bars = document.getElementById('jev-bars');
  for (const name of ['up', 'down', 'left', 'right']) {
    const row = document.createElement('div');
    row.className = 'jev-row';
    row.innerHTML = `
      <span class="jev-line">
        <span class="jev-label">${name}</span>
        <span class="jev-val" id="jev-val-${name}">0%%</span>
      </span>
      <span class="jev-track"><span class="jev-fill" id="jev-fill-${name}"></span></span>`;
    bars.appendChild(row);
  }

  window.__jev = (data) => {
    for (const name of ['up', 'down', 'left', 'right']) {
      const share = data.probabilities[name] || 0;
      const fill = document.getElementById('jev-fill-' + name);
      fill.style.width = (share * 100).toFixed(0) + '%%';
      // Red marks a direction Jev itself judged likely to be fatal.
      fill.classList.toggle('danger', (data.danger[name] || 0) > 0.5);
      document.getElementById('jev-val-' + name).textContent = (share * 100).toFixed(0) + '%%';
    }
  };
  return {left: rect.left, top: rect.top, width: rect.width, height: rect.height};
}
""" % {"width": PANEL_WIDTH}
