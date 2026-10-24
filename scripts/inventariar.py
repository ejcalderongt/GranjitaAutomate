"""Actualizar el inventario local sin imprimir identificadores privados."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from granjita.inventory import FleetStore, scan_fleet, collect_inventory


def main():
    store = FleetStore()
    ports = [int(p) for p in store.setting('ports', '5037,5038').split(',')]
    report = scan_fleet(ports)
    store.save_fleet(report)
    rows = [r for r in store.fleet_devices() if r['status'] == 'Validado']
    counts = Counter()
    roots = Counter()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(lambda r: collect_inventory(r['port'], r['serial']), rows)
        for row, observations in zip(rows, results):
            store.save_inventory(row['id'], row['port'], row['serial'], observations)
            counts.update(o['state'] for o in observations)
            roots.update(o['value'] for o in observations if o['field'] == 'Evaluación de root')
    print('Capturas:', len(rows))
    print('Resultados:', dict(counts))
    print('Root:', dict(roots))


if __name__ == '__main__':
    main()
