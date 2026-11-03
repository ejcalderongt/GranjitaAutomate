"""Panel nativo QA. Tk solo se modifica desde su hilo principal."""
import asyncio
from datetime import datetime
import logging
from pathlib import Path
import queue
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from uuid import uuid4

from core.browser import ROOT
from core.poc_runner import POCSettings, ejecutar_poc
from core.telemetry import DEFAULT_DB, inicializar_db_telemetria, registrar_evento_poc

LOGGER_NAMES = ('warmer.geo','warmer.ai','warmer.scraper','qa.load_testing','qa.telemetry','qa.poc')
logger = logging.getLogger('qa.poc')


def format_metric(value):
    if value is None:
        return '—'
    if isinstance(value,float):
        return f'{value:,.2f}'
    return {'passed':'Correcto','failed':'Con fallo','cancelled':'Cancelado','running':'En curso'}.get(value,value)


def cycle_progress(rows, target):
    """Cuenta ciclos correctos únicos, nunca checkpoints ni ciclos iniciados."""
    latest = {}
    for row in rows:
        latest[row.get('cycle_id',row['ciclo_numero'])] = row
    done = min(target,sum(row['estado_ciclo']=='passed' for row in latest.values()))
    return done,100*done/target if target > 0 else 0


def log_tag(message):
    text = str(message).lower()
    if any(word in text for word in ('fallo','fallido','error','no se pudo','no confirmada','no acreditada')):
        return 'error'
    if any(word in text for word in ('persistid','guardad','sqlite','verificado')):
        return 'persisted'
    if any(word in text for word in ('aviso','pendiente','cancel','parada','agotada')):
        return 'warning'
    return 'info'


def presentar_ventana(root, *, topmost_ms=600):
    """Solicitar visibilidad una vez; Windows conserva la decisión sobre el foco."""
    callbacks = []
    original = None

    def restore():
        try:
            if original is not None and root.winfo_exists():
                root.attributes('-topmost',original)
        except tk.TclError:
            pass

    def show():
        nonlocal original
        try:
            if not root.winfo_exists():
                return
            original = root.attributes('-topmost')
            root.deiconify()
            root.attributes('-topmost',True)
            root.lift()
            root.focus_set()
            logger.info('Ventana QA presentada; elevación temporal programada')
        except tk.TclError:
            logger.warning('Windows/Tk no confirmó la presentación de la ventana')
        finally:
            try:
                if root.winfo_exists():
                    callbacks.append(root.after(topmost_ms,restore))
            except tk.TclError:
                restore()

    callbacks.append(root.after_idle(show))

    def release():
        for callback in callbacks:
            try:
                root.after_cancel(callback)
            except tk.TclError:
                pass
        restore()
    return release


def configurar_logs_terminal():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s'))
    for name in LOGGER_NAMES:
        target = logging.getLogger(name)
        target.setLevel(logging.INFO)
        target.addHandler(handler)
    return handler


class QueueLogHandler(logging.Handler):
    def __init__(self, notify):
        super().__init__(logging.INFO)
        self.notify = notify

    def emit(self, record):
        text = record.getMessage()
        text = re.sub(r'(?i)([a-z]+://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',text)
        text = re.sub(r'sk-[A-Za-z0-9_-]+','[REDACTED]',text)
        self.notify('log',text[:1500])


class POCController:
    def __init__(self, notify, runner=ejecutar_poc):
        self.notify, self.runner = notify, runner
        self.stop = threading.Event()
        self.login_ready = threading.Event()
        self.thread = self.loop = self.task = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, settings, db_path):
        if self.running:
            return False
        settings.validate()
        self.stop.clear()
        self.login_ready.clear()

        async def run():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            try:
                await self.runner(settings,self.stop,self.login_ready,self.notify,db_path)
            except asyncio.CancelledError:
                self.notify('log','Parada cooperativa completada')
            except Exception as exc:
                self.notify('log','No se pudo completar la POC: '+type(exc).__name__)
                self.notify('result',{'clean':False,'failed':True,'cancelled':self.stop.is_set()})
            finally:
                self.task = None
                self.loop = None
                self.notify('finished',None)

        self.thread = threading.Thread(target=lambda:asyncio.run(run()),name='qa-poc-worker',daemon=False)
        self.thread.start()
        return True

    def cancel(self):
        already_requested = self.stop.is_set()
        self.stop.set()
        if already_requested:
            return
        loop = self.loop
        if loop is not None and loop.is_running():
            def schedule_cancel():
                # La retención tiene tiempo de registrar su evento; una consulta
                # de red en curso se cancela sin esperar su timeout completo.
                def cancel_pending():
                    if self.task is not None and not self.task.done():
                        self.task.cancel()
                loop.call_later(.15,cancel_pending)
            try:
                loop.call_soon_threadsafe(schedule_cancel)
            except RuntimeError:
                pass


class DashboardPOC:
    def __init__(self, root, *, telemetry_db=DEFAULT_DB):
        self.root = root
        self.events = queue.Queue()
        self.target_cycles = 5
        self.controller = POCController(self.notify)
        self.closing = False
        self.can_restart = True
        self.application_run_id = 'ui-'+uuid4().hex
        self.close_audit_thread = None
        self.close_audit_done = threading.Event()
        self.telemetry_db = inicializar_db_telemetria(telemetry_db)
        root.title('AGX · Laboratorio QA — POC web')
        root.geometry('1100x940')
        root.minsize(980,850)
        root.configure(bg='#f2f5f9')
        self.account = tk.StringVar(value='cuenta_tiktok_01')
        self.base = tk.DoubleVar(value=6)
        self.cycles = tk.IntVar(value=5)
        self.selectors = tk.StringVar(value=str(ROOT/'config/web_selectors.mobile.json'))
        self.europe = tk.BooleanVar(value=True)
        self.mobile_rotation = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='LISTO · sin ejecución activa')
        self.build()
        self.handler = QueueLogHandler(self.notify)
        self.loggers = [logging.getLogger(name) for name in LOGGER_NAMES]
        self.logger_levels = [logger.level for logger in self.loggers]
        for logger in self.loggers:
            logger.addHandler(self.handler)
            logger.setLevel(logging.INFO)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)
        self.release_presentation = presentar_ventana(root)

    def build(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TFrame',background='#f2f5f9')
        style.configure('Card.TFrame',background='#ffffff')
        style.configure('TLabel',background='#ffffff',foreground='#475569',font=('Segoe UI',10))
        style.configure('Title.TLabel',background='#f2f5f9',foreground='#0f172a',font=('Segoe UI',24,'bold'))
        style.configure('CardTitle.TLabel',foreground='#0f172a',font=('Segoe UI',12,'bold'))
        style.configure('Sub.TLabel',background='#f2f5f9',foreground='#64748b')
        style.configure('TCheckbutton',background='#ffffff',foreground='#334155',padding=4)
        style.configure('TEntry',padding=7)
        style.configure('TButton',font=('Segoe UI',10,'bold'),padding=(18,11))
        for name,color,hover in [('Start','#216b62','#19594f'),('Continue','#355d83','#284c6e'),('Stop','#aa3845','#922d39')]:
            style.configure(name+'.TButton',background=color,foreground='white',borderwidth=0)
            style.map(name+'.TButton',background=[('disabled','#e2e8f0'),('active',hover)],
                      foreground=[('disabled','#94a3b8')])
        style.configure('Treeview',rowheight=34,font=('Segoe UI',10),background='white',fieldbackground='white',foreground='#334155',borderwidth=0)
        style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),padding=9,background='#edf2f7',foreground='#475569')
        style.configure('QA.Horizontal.TProgressbar',background='#216b62',troughcolor='#e2e8f0',borderwidth=0)
        content = ttk.Frame(self.root,padding=(24,18))
        content.pack(fill='both',expand=True)
        content.columnconfigure(0,weight=1)
        content.rowconfigure(3,weight=3)
        content.rowconfigure(4,weight=2)
        header = ttk.Frame(content)
        header.grid(row=0,column=0,sticky='ew',pady=(0,14))
        ttk.Label(header,text='AGX · Laboratorio de auditoría',style='Title.TLabel').pack(anchor='w')
        tk.Label(header,text='🛡️ MODO DE AUDITORÍA ACTIVO: SOLO LECTURA Y DESPLAZAMIENTO',
            bg='#dceee9',fg='#175e51',font=('Segoe UI',10,'bold'),padx=12,pady=9).pack(fill='x',pady=(9,0))
        top = ttk.Frame(content)
        top.grid(row=1,column=0,sticky='ew')
        top.columnconfigure(0,weight=1,uniform='cards')
        top.columnconfigure(1,weight=1,uniform='cards')
        identity = ttk.Frame(top,style='Card.TFrame',padding=16)
        identity.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        identity.columnconfigure(1,weight=1)
        ttk.Label(identity,text='01  Identidad y sesión',style='CardTitle.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        self.config_widgets = []
        for row,(label,var) in enumerate([('Cuenta persistente',self.account),('Ciclos de auditoría (1–100)',self.cycles),('Retención por video (segundos)',self.base)],1):
            ttk.Label(identity,text=label).grid(row=row,column=0,sticky='w',pady=4,padx=(0,10))
            entry=ttk.Entry(identity,textvariable=var,width=23)
            entry.grid(row=row,column=1,sticky='ew',pady=4)
            self.config_widgets.append(entry)
        ttk.Label(identity,text='La retención total se ajusta al texto, con un máximo de 30 s.',wraplength=410).grid(row=4,column=0,columnspan=2,sticky='w',pady=(6,0))
        self.advanced_button=ttk.Button(identity,text='▸ Opciones avanzadas',command=self.toggle_advanced)
        self.advanced_button.grid(row=5,column=0,columnspan=2,sticky='w',pady=(5,0))
        self.advanced=ttk.Frame(identity,style='Card.TFrame')
        self.advanced.grid(row=6,column=0,columnspan=2,sticky='ew',pady=(8,0))
        self.advanced.columnconfigure(0,weight=1)
        ttk.Label(self.advanced,text='Configuración de selectores').grid(row=0,column=0,sticky='w')
        entry=ttk.Entry(self.advanced,textvariable=self.selectors)
        entry.grid(row=1,column=0,sticky='ew')
        self.config_widgets.append(entry)
        self.advanced.grid_remove()
        network = ttk.Frame(top,style='Card.TFrame',padding=16)
        network.grid(row=0,column=1,sticky='nsew',padx=(8,0))
        ttk.Label(network,text='02  Red y seguridad',style='CardTitle.TLabel').pack(anchor='w',pady=(0,8))
        self.network_labels={}
        for key,title in [('proxy','Proxy configurado · SOCKS5 esperado'),('geo','Filtro continental · Europa')]:
            ttk.Label(network,text=title,font=('Segoe UI',10,'bold')).pack(anchor='w',pady=(6,3))
            label=tk.Label(network,text='○ Sin comprobar',bg='#eef2f7',fg='#475569',anchor='w',
                justify='left',padx=10,pady=7,wraplength=410,font=('Segoe UI',10))
            label.pack(fill='x')
            self.network_labels[key]=label
        for title,var in [('Exigir salida europea verificada',self.europe),('Verificar proxy antes de navegar',self.mobile_rotation)]:
            check=ttk.Checkbutton(network,text=title,variable=var)
            check.pack(anchor='w',pady=(5,0))
            self.config_widgets.append(check)
        controls=ttk.Frame(content)
        controls.grid(row=2,column=0,sticky='ew',pady=14)
        self.start_button=ttk.Button(controls,text='Iniciar POC',style='Start.TButton',command=self.start)
        self.start_button.pack(side='left')
        self.login_button=ttk.Button(controls,text='Continuar tras login',style='Continue.TButton',command=self.continue_login,state='disabled')
        self.login_button.pack(side='left',padx=10)
        self.cancel_button=ttk.Button(controls,text='Parada segura',style='Stop.TButton',command=self.cancel,state='disabled')
        self.cancel_button.pack(side='right')
        audit=ttk.Frame(content,style='Card.TFrame',padding=16)
        audit.grid(row=3,column=0,sticky='nsew')
        audit.columnconfigure(0,weight=1)
        audit.rowconfigure(2,weight=1)
        ttk.Label(audit,text='03  Auditoría de ciclos',style='CardTitle.TLabel').grid(row=0,column=0,sticky='w')
        ttk.Label(audit,textvariable=self.status).grid(row=1,column=0,sticky='w',pady=(4,10))
        columns=('cycle','dom','api','hold','state')
        self.metrics=ttk.Treeview(audit,columns=columns,show='headings',height=5)
        for key,label,width in zip(columns,('Ciclo','Lectura DOM (ms)','OpenAI (ms)','Retención (s)','Resultado'),(70,160,150,140,180)):
            self.metrics.heading(key,text=label)
            self.metrics.column(key,width=width,minwidth=65,anchor='w')
        self.metrics.tag_configure('passed',foreground='#17614f',background='#f0faf5')
        self.metrics.tag_configure('failed',foreground='#a12f40',background='#fff1f2')
        self.metrics.tag_configure('cancelled',foreground='#925d16',background='#fff8e8')
        self.metrics.grid(row=2,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(audit,command=self.metrics.yview)
        scrollbar.grid(row=2,column=1,sticky='ns')
        self.metrics.configure(yscrollcommand=scrollbar.set)
        self.progress=ttk.Progressbar(audit,maximum=100,style='QA.Horizontal.TProgressbar')
        self.progress.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(12,4))
        self.progress_text=tk.StringVar(value='0 de 5 ciclos correctos · 0%')
        ttk.Label(audit,textvariable=self.progress_text).grid(row=4,column=0,sticky='w')
        logs=ttk.Frame(content,style='Card.TFrame',padding=14)
        logs.grid(row=4,column=0,sticky='nsew',pady=(12,0))
        logs.columnconfigure(0,weight=1)
        logs.rowconfigure(1,weight=1)
        ttk.Label(logs,text='Consola de ejecución',style='CardTitle.TLabel').grid(row=0,column=0,sticky='w',pady=(0,6))
        self.console=tk.Text(logs,bg='#142132',fg='#d4dce8',font=('Consolas',9),height=6,
            wrap='word',relief='flat',padx=12,pady=10,state='disabled')
        self.console.grid(row=1,column=0,sticky='nsew')
        for tag,color in [('info','#d4dce8'),('persisted','#86d9bf'),('warning','#f6cd84'),('error','#ff9fac')]:
            self.console.tag_configure(tag,foreground=color)
        scroll=ttk.Scrollbar(logs,command=self.console.yview)
        scroll.grid(row=1,column=1,sticky='ns')
        self.console.configure(yscrollcommand=scroll.set)

    def toggle_advanced(self):
        visible=bool(self.advanced.winfo_manager())
        if visible:
            self.advanced.grid_remove()
        else:
            self.advanced.grid()
        self.advanced_button.configure(text='▸ Opciones avanzadas' if visible else '▾ Ocultar opciones avanzadas')

    def show_network(self, data):
        label=self.network_labels.get(data.get('component'))
        if label is None:
            return
        palette={'checking':('#fff5db','#805e16','◌ '),'verified':('#e3f3eb','#17614f','✓ '),
                 'failed':('#fde8eb','#9c293b','⚠ '),'info':('#e9eff8','#355d83','○ ')}
        bg,fg,icon=palette.get(data.get('state'),('#eef2f7','#475569','○ '))
        label.configure(text=icon+data.get('message','Sin comprobar'),bg=bg,fg=fg)

    def render_metrics(self, rows):
        self.metrics.delete(*self.metrics.get_children())
        for row in sorted(rows,key=lambda r:r['ciclo_numero']):
            values=(row['ciclo_numero'],row['latencia_dom_ms'],row['latencia_openai_ms'],
                    row['tiempo_retencion_ejecutado_seg'],row['estado_ciclo'])
            self.metrics.insert('','end',values=tuple(format_metric(value) for value in values),tags=(row['estado_ciclo'],))
        completed,percent=cycle_progress(rows,self.target_cycles)
        self.progress['value']=percent
        self.progress_text.set(f'{completed} de {self.target_cycles} ciclos correctos · {percent:.0f}%')

    def notify(self, kind, data):
        try:
            if kind == 'log' and self.events.qsize() >= 1000:
                return
            self.events.put_nowait((kind,data))
        except queue.Full:
            pass

    def start(self):
        if self.controller.running or not self.can_restart:
            return
        try:
            settings = POCSettings(self.account.get().strip(),float(self.base.get()),int(self.cycles.get()),
                Path(self.selectors.get().strip()).resolve(),bool(self.europe.get()),rotate_mobile=bool(self.mobile_rotation.get()))
            settings.validate()
            if self.controller.start(settings,self.telemetry_db):
                logger.info('Inicio solicitado; el worker registrará la admisión en SQLite')
                self.target_cycles = settings.cycles
                self.render_metrics([])
                for component in ('proxy','geo'):
                    self.show_network({'component':component,'state':'info','message':'Pendiente de comprobación'})
                for widget in self.config_widgets:
                    widget.configure(state='disabled')
                self.start_button.configure(state='disabled')
                self.cancel_button.configure(state='normal')
                self.status.set('EN CURSO · preparando navegador')
                self.can_restart = False
        except (ValueError,tk.TclError) as exc:
            messagebox.showerror('Configuración inválida',str(exc),parent=self.root)

    def continue_login(self):
        if not self.controller.running or self.closing:
            return
        logger.info('Continuación tras login solicitada por el operador')
        self.controller.login_ready.set()
        self.login_button.configure(state='disabled')
        self.status.set('EN CURSO · midiendo ciclos QA')

    def cancel(self):
        logger.info('Parada segura solicitada; esperando cierres y auditoría SQLite')
        self.controller.cancel()
        self.cancel_button.configure(state='disabled')
        self.login_button.configure(state='disabled')
        self.status.set('DETENIENDO · cierre seguro de recursos')

    def poll(self):
        for _ in range(100):
            try:
                kind,data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                self.console.configure(state='normal')
                self.console.insert('end',datetime.now().strftime('%H:%M:%S')+'  '+str(data)+'\n',log_tag(data))
                if int(self.console.index('end-1c').split('.')[0]) > 1500:
                    self.console.delete('1.0','300.0')
                self.console.see('end')
                self.console.configure(state='disabled')
            elif kind == 'login':
                self.status.set('INTERVENCIÓN MANUAL · revisar navegador')
                self.login_button.configure(state='normal')
                self.notify('log',data)
            elif kind == 'cycle':
                self.status.set('EN CURSO · ciclo '+str(data))
            elif kind == 'metrics':
                self.render_metrics(data)
            elif kind == 'network':
                self.show_network(data)
            elif kind == 'result':
                self.can_restart = data['clean'] and data.get('telemetry_saved',True)
                state = 'CANCELADO' if data['cancelled'] else 'CON FALLOS' if data['failed'] else 'FINALIZADO'
                self.status.set(state+' · '+('cierre y auditoría confirmados' if self.can_restart else 'revisar recursos o auditoría pendientes'))
            elif kind == 'finished':
                self.cancel_button.configure(state='disabled')
                self.login_button.configure(state='disabled')
                if self.can_restart and not self.closing:
                    self.start_button.configure(state='normal')
                    for widget in self.config_widgets:
                        widget.configure(state='normal')
        if self.closing and not self.controller.running and self.close_audit_thread is None:
            clean = self.can_restart
            def close_audit():
                try:
                    registrar_evento_poc(self.application_run_id,'qa_desktop',
                        'cierre_exitoso' if clean else 'cierre_fallido','completado' if clean else 'fallido',
                        db_path=self.telemetry_db)
                except Exception as exc:
                    logger.error('Cierre de interfaz: auditoría SQLite no confirmada (%s)',type(exc).__name__)
                finally:
                    self.close_audit_done.set()
            self.close_audit_thread = threading.Thread(target=close_audit,name='qa-ui-close-audit',daemon=False)
            self.close_audit_thread.start()
        if self.closing and not self.controller.running and self.close_audit_done.is_set():
            for logger,level in zip(self.loggers,self.logger_levels):
                logger.removeHandler(self.handler)
                logger.setLevel(level)
            self.root.destroy()
            return
        self.root.after(100,self.poll)

    def close(self):
        self.release_presentation()
        self.closing = True
        self.start_button.configure(state='disabled')
        self.cancel()


def main():
    handler = configurar_logs_terminal()
    try:
        root = tk.Tk()
        DashboardPOC(root)
        root.mainloop()
    finally:
        for name in LOGGER_NAMES:
            logging.getLogger(name).removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    main()
