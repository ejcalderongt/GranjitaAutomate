import unittest
from ui.poc_dashboard import cycle_progress, log_tag, format_metric


class VisualStateTests(unittest.TestCase):
    def test_progress_counts_successes_not_checkpoints_or_failures(self):
        rows=[{'cycle_id':'a','ciclo_numero':1,'estado_ciclo':'running'},
              {'cycle_id':'a','ciclo_numero':1,'estado_ciclo':'passed'},
              {'cycle_id':'b','ciclo_numero':2,'estado_ciclo':'failed'},
              {'cycle_id':'c','ciclo_numero':3,'estado_ciclo':'cancelled'}]
        self.assertEqual(cycle_progress(rows,5),(1,20))
        self.assertEqual(cycle_progress([],5),(0,0))

    def test_failure_takes_precedence_over_sqlite_color(self):
        self.assertEqual(log_tag('SQLite no confirmada: fallo de persistencia'),'error')
        self.assertEqual(log_tag('Evento POC persistido'),'persisted')
        self.assertEqual(log_tag('Parada solicitada'),'warning')
        self.assertEqual(format_metric(None),'—')
