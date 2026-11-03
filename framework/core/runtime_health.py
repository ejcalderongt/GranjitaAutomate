"""Admisión API recuperable: matar un worker no deja semáforos adquiridos."""
import time


class ParadaRecuperable:
    """Bandera compartida sin lock que pueda quedar adquirido al terminar un worker."""
    def __init__(self,context):
        self.flag=context.RawValue('b',0)

    def is_set(self):
        return bool(self.flag.value)

    def set(self):
        self.flag.value=1

    def wait(self,timeout=None):
        deadline=None if timeout is None else time.monotonic()+timeout
        while not self.is_set():
            remaining=.1 if deadline is None else deadline-time.monotonic()
            if remaining<=0:
                return False
            time.sleep(min(.1,remaining))
        return True


class ClienteRecuperable:
    def __init__(self,client,database,token,run_id,device_id,stop,rpm,concurrency,heartbeat=None):
        from types import SimpleNamespace
        self.client,self.db,self.token=client,database,token
        self.run_id,self.device_id,self.stop=run_id,device_id,stop
        self.rpm,self.concurrency=rpm,concurrency
        self.heartbeat=heartbeat
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self,**kwargs):
        acquired=False
        heartbeat=0
        while not self.stop.is_set():
            now=time.time()
            with self.db.conexion() as con:
                con.execute('BEGIN IMMEDIATE')
                con.execute('DELETE FROM api_slots WHERE expires<?',(now,))
                count=con.execute('SELECT COUNT(*) FROM api_slots').fetchone()[0]
                row=con.execute('SELECT next_start FROM api_rate WHERE run_id=?',(self.run_id,)).fetchone()
                if count<self.concurrency and (not row or row['next_start']<=now):
                    con.execute('INSERT INTO api_slots VALUES (?,?,?)',(self.token,self.run_id,now+120))
                    con.execute('INSERT INTO api_rate VALUES (?,?) ON CONFLICT(run_id) DO UPDATE SET next_start=excluded.next_start',
                                (self.run_id,now+60/self.rpm))
                    acquired=True
            if acquired:
                break
            if now-heartbeat>=5:
                if self.heartbeat is not None:
                    self.heartbeat()
                else:
                    self.db.actualizar_dispositivo(self.device_id,estado='Analizando con IA',conectado=True)
                heartbeat=now
            self.stop.wait(.25)
        if not acquired:
            raise InterruptedError('Consulta IA cancelada')
        try:
            if self.stop.is_set():
                raise InterruptedError('Consulta IA cancelada')
            return self.client.chat.completions.create(**kwargs)
        finally:
            liberar_api(self.db,self.token)


def liberar_api(database,token):
    with database.conexion() as con:
        con.execute('DELETE FROM api_slots WHERE token=?',(token,))
