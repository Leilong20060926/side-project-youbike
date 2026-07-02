document.addEventListener('DOMContentLoaded', () => {
  const map = L.map('map').setView([25.0330, 121.5654], 13);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  L.marker([25.0330, 121.5654]).addTo(map).bindPopup('台北市').openPopup();

  const setupPage = document.getElementById('page-setup');
  const resultPage = document.getElementById('page-result');
  const nextStepBtn = document.getElementById('next-step-btn');
  const backBtn = document.getElementById('back-btn');
  const hintBox = document.getElementById('bonus-hint');
  const routeItems = document.querySelectorAll('.route-item');

  function showPage(targetPage) {
    setupPage.classList.toggle('hidden', targetPage !== 'setup');
    resultPage.classList.toggle('hidden', targetPage !== 'result');
  }

  function updateHint() {
    const bikeType = document.querySelector('input[name="bike-type"]:checked')?.value;
    const priority = document.querySelector('input[name="route-priority"]:checked')?.value;

    if (bikeType === 'ebike' && priority === 'time') {
      hintBox.textContent = '前 30 分鐘免費補助提醒：建議優先使用電輔車縮短騎乘時間。';
    } else if (bikeType === 'standard' && priority === 'flat') {
      hintBox.textContent = '中途還車再借轉乘點建議：可避開陡坡並降低步行負擔。';
    } else {
      hintBox.textContent = '前 30 分鐘免費補助提醒，或中途還車再借轉乘點建議。';
    }
  }

  nextStepBtn.addEventListener('click', () => {
    showPage('result');
  });

  backBtn.addEventListener('click', () => {
    showPage('setup');
  });

  document.querySelectorAll('input[name="bike-type"], input[name="route-priority"]').forEach((input) => {
    input.addEventListener('change', updateHint);
  });

  routeItems.forEach((item) => {
    item.addEventListener('click', () => {
      routeItems.forEach((route) => route.classList.remove('active'));
      item.classList.add('active');
    });
  });

  updateHint();
});
