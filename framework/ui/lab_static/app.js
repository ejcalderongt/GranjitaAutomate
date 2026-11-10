const $ = id => document.getElementById(id);
const labels = {
    idle: 'Listo', running: 'En curso', completed: 'Completado',
    cancelled: 'Cancelado', failed: 'Con fallo', unchecked: 'Sin comprobar',
    preflight: 'Verificando', blocked: 'Lote bloqueado', incident: 'Incidente detectado'
};
const networkLabels = {
    unchecked: ['--', 'Sin comprobar'], identity_unverified: ['--', 'Identidad sin verificar'],
    network_failed: ['Fallo', 'Excluida'], https_ok: ['HTTPS', 'Red verificada'],
    ping_ok: ['Ping', 'Conectividad basica']
};
const date = value => value ? new Date(value).toLocaleString('es-GT') : '--';

async function api(path, method = 'GET') {
    const headers = method === 'POST' ? {'X-Lab-Action': 'synthetic'} : {};
    const response = await fetch(path, {method, headers});
    if (!response.ok) throw Error('Solicitud no disponible (' + response.status + ')');
    return response.json();
}

function renderDashboard(state) {
    $('overall').textContent = labels[state.state] || '--';
    for (const name of ['online', 'ready', 'alerts']) {
        $(name).textContent = state[name] ?? '--';
    }
    $('cost').textContent = state.estimated_usd == null
        ? '--' : 'USD ' + state.estimated_usd.toFixed(4);
    $('checked-at').textContent = state.checked_at
        ? 'Comprobado: ' + date(state.checked_at) : 'Esperando la primera comprobacion de placas.';
    $('inventory').replaceChildren(...state.devices.map(device => {
        const row = document.createElement('tr');
        const [network, status] = networkLabels[device.network];
        row.dataset.network = device.network;
        const profile = [device.app, device.locale, device.timezone];
        const pending = profile.includes('manual');
        const details = profile.map(value => value === 'ok' ? 'OK' : value === 'manual' ? 'Ajustar' : '--');
        row.dataset.pending = pending;
        for (const value of [device.alias, device.plate, network, ...details, date(device.last_run),
                            pending ? 'Requiere ajuste' : status]) {
            const cell = document.createElement('td');
            cell.textContent = value;
            row.appendChild(cell);
        }
        return row;
    }));
    $('inventory-status').textContent = state.devices.length ? '' : 'Aun no hay placas registradas.';
}

async function refresh() {
    try {
        const state = await api('/api/status');
        renderDashboard(state.dashboard);
        $('status').textContent = labels[state.status];
        $('reason').textContent = state.status === 'idle'
            ? 'Comprueba la politica con datos sinteticos.' : 'Estado de la verificacion sintetica.';
        $('verify').disabled = state.status === 'running';
        $('stop').disabled = state.status !== 'running';
        if (!$('advanced').open) return;
        const files = await api('/api/evidence');
        $('files').replaceChildren(...files.map(file => {
            const button = document.createElement('button');
            button.textContent = (file.synthetic ? 'SINTETICO / ' : 'REAL / ') + file.id;
            button.onclick = async () => {
                try {
                    const result = await api('/api/evidence/' + encodeURIComponent(file.id));
                    $('detail').textContent = JSON.stringify(result, null, 2);
                } catch (error) {
                    $('error').textContent = error.message;
                }
            };
            return button;
        }));
        if (!files.length) $('files').textContent = 'Aun no hay evidencia permitida.';
    } catch (error) {
        $('error').textContent = error.message;
    }
}

for (const action of ['verify', 'stop']) {
    $(action).onclick = async () => {
        try {
            await api('/api/actions/' + action, 'POST');
            await refresh();
        } catch (error) {
            $('error').textContent = error.message;
        }
    };
}
$('advanced').addEventListener('toggle', refresh);
refresh();
setInterval(refresh, 3000);
