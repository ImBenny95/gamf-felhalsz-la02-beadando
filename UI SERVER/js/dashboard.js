const loginDiv = document.getElementById('loginDiv');
const dashboardDiv = document.getElementById('dashboardDiv');
const loginBtn = document.getElementById('loginBtn');
const logoutBtn = document.getElementById('logoutBtn');
const loginError = document.getElementById('loginError');
const sitesTable = document.getElementById('sitesTable');

const addSiteBtn = document.getElementById('addSiteBtn');
const newSiteName = document.getElementById('newSiteName');
const newSiteUrl = document.getElementById('newSiteUrl');
const addSiteError = document.getElementById('addSiteError');

// Ellenőrizzük, van-e token
if (localStorage.getItem('token')) {
    showDashboard();
}

// Bejelentkezés
loginBtn.addEventListener('click', async () => {
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;
    loginError.textContent = '';
    try {
        const data = await login(username, password);
        localStorage.setItem('token', data.token);
        showDashboard();
    } catch (err) {
        loginError.textContent = err.message;
    }
});

// Kijelentkezés
logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('token');
    dashboardDiv.classList.add('hidden');
    loginDiv.classList.remove('hidden');
});

// Új weboldal hozzáadása
addSiteBtn.addEventListener('click', async () => {
    addSiteError.textContent = '';
    const name = newSiteName.value.trim();
    const url = newSiteUrl.value.trim();
    if (!name || !url) {
        addSiteError.textContent = "Adj meg nevet és URL-t!";
        return;
    }
    try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/sites', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ name, url })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || 'Hiba a hozzáadáskor');
        }
        newSiteName.value = '';
        newSiteUrl.value = '';
        await loadSites();
    } catch (err) {
        addSiteError.textContent = err.message;
    }
});

async function showDashboard() {
    loginDiv.classList.add('hidden');
    dashboardDiv.classList.remove('hidden');
    await loadSites();
}

async function loadSites() {
    try {
        const sites = await getSites();
        sitesTable.innerHTML = '';
        for (const s of sites) {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${s.name}</td>
                <td><a href="${s.url}" target="_blank">${s.url}</a></td>
                <td class="${s.last_status ? 'up' : 'down'}">${s.last_status ? 'UP' : 'DOWN'}</td>
                <td>${s.last_checked || '-'}</td>
                <td>${s.last_status ? '-' : (s.down_since || '-')}</td>
                <td><button class="delete-btn" data-id="${s.id}">Törlés</button></td>
            `;
            sitesTable.appendChild(tr);
        }

        // Delete gombok esemény kezelése
        document.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const siteId = btn.dataset.id;
                if (!confirm("Biztos törlöd ezt az oldalt?")) return;
                try {
                    const token = localStorage.getItem('token');
                    const res = await fetch(`/api/sites/${siteId}`, {
                        method: 'DELETE',
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (!res.ok) throw new Error('Hiba a törléskor');
                    await loadSites();
                } catch (err) {
                    alert(err.message);
                }
            });
        });

    } catch (err) {
        sitesTable.innerHTML = `<tr><td colspan="6" class="error">${err.message}</td></tr>`;
    }
}
