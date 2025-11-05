// Az UI szerver proxyja
const API_URL = '/api';

// Bejelentkezés
async function login(username, password) {
    const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Hiba a bejelentkezésnél');
    }
    return await response.json();
}

// Weboldalak lekérése
async function getSites() {
    const token = localStorage.getItem('token');
    const response = await fetch(`${API_URL}/sites`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Hiba a weboldalak lekérdezésekor');
    }
    return await response.json();
}

// Statisztikák lekérdezése (opcionális)
async function getStats() {
    const token = localStorage.getItem('token');
    const response = await fetch(`${API_URL}/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || 'Hiba a statisztikák lekérdezésekor');
    }
    return await response.json();
}
