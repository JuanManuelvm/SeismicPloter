import tkinter as tk
from tkinter import ttk, scrolledtext
from obspy.clients.seedlink.easyseedlink import EasySeedLinkClient
from obspy import UTCDateTime
import threading
import subprocess
from datetime import datetime, timedelta
import urllib3

# Importar el graficador (asegúrate de tenerlo en el mismo directorio o en PYTHONPATH)
from seismic_plotter import SeismicPlotter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SeedLinkMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Monitor Sísmico")
        self.root.geometry("1400x800")
        
        # Configuración
        self.server_host = "192.168.84.112"
        self.stations = []
        self.active_connections = {}
        self.client = None
        self.client_thread = None
        self.running = False
        self.update_interval = 1000
        self.selected_stations = []
        self.station_vars = {}

        # Interfaz gráfica
        self.setup_ui()
        self.load_station_info()

    def setup_ui(self):
        """Configura la interfaz gráfica simplificada"""
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Panel dividido
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # --- Panel izquierdo (Estaciones activas EHZ/HNZ) ---
        left_frame = ttk.Frame(paned_window, padding=5)
        paned_window.add(left_frame, weight=1)
        
        ttk.Label(left_frame, text="Estaciones Activas (EHZ/HNZ)", 
                 font=('Helvetica', 10, 'bold')).pack(pady=5)
        
        # Treeview para estaciones activas
        columns = ('select', 'network', 'station', 'channel', 'status')
        self.station_tree = ttk.Treeview(
            left_frame,
            columns=columns,
            show='headings',
            height=25
        )
        
        # Configurar columnas
        self.station_tree.heading('select', text='Seleccionar')
        self.station_tree.heading('network', text='Red')
        self.station_tree.heading('station', text='Estación')
        self.station_tree.heading('channel', text='Canal')
        self.station_tree.heading('status', text='Estado')
        
        self.station_tree.column('select', width=80, anchor=tk.CENTER)
        self.station_tree.column('network', width=100, anchor=tk.W)
        self.station_tree.column('station', width=150, anchor=tk.W)
        self.station_tree.column('channel', width=80, anchor=tk.W)
        self.station_tree.column('status', width=150, anchor=tk.W)
        
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.station_tree.yview)
        self.station_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.station_tree.pack(fill=tk.BOTH, expand=True)
        
        # Configurar checkboxes
        self.station_tree.tag_configure('checkbox', background='white')
        self.station_tree.bind('<Button-1>', self.on_treeview_click)
        
        # --- Panel derecho (Información completa) ---
        right_frame = ttk.Frame(paned_window, padding=5)
        paned_window.add(right_frame, weight=2)
        
        ttk.Label(right_frame, text="Información Completa de Estaciones", 
                 font=('Helvetica', 10, 'bold')).pack(pady=5)
        
        # Treeview para información completa
        info_columns = ('network', 'station', 'location', 'channel', 'type', 
                       'start_time', 'end_time', 'status')
        self.info_tree = ttk.Treeview(
            right_frame,
            columns=info_columns,
            show='headings',
            height=25
        )
        
        for col in info_columns:
            self.info_tree.heading(col, text=col.capitalize())
            self.info_tree.column(col, width=120, anchor=tk.W)
        
        info_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.info_tree.yview)
        self.info_tree.configure(yscroll=info_scrollbar.set)
        info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.info_tree.pack(fill=tk.BOTH, expand=True)
        
        # --- Panel de controles simplificado ---
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Botón para enviar estaciones a la otra aplicación
        ttk.Button(
            control_frame,
            text="Enviar estaciones seleccionadas",
            command=self.send_to_application,
            style='Accent.TButton'
        ).pack(side=tk.LEFT, padx=5)
        
        # Botón para actualizar información
        ttk.Button(
            control_frame,
            text="Actualizar información",
            command=self.load_station_info
        ).pack(side=tk.LEFT, padx=5)
        
        # Consola de logs
        self.log_console = scrolledtext.ScrolledText(
            main_frame,
            height=8,
            wrap=tk.WORD,
            font=('Consolas', 9)
        )
        self.log_console.pack(fill=tk.BOTH, pady=(10, 0))
        
        # Barra de estado
        self.status_var = tk.StringVar(value="Listo")
        status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            padding=5
        )
        status_bar.pack(fill=tk.X)

    def on_treeview_click(self, event):
        """Maneja la selección de estaciones"""
        region = self.station_tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.station_tree.identify_column(event.x)
            if column == "#1":  # Columna de selección
                item = self.station_tree.identify_row(event.y)
                values = self.station_tree.item(item, 'values')
                station_key = f"{values[1]}.{values[2]}"
                current_val = self.station_vars.get(station_key, False)
                self.station_vars[station_key] = not current_val
                self.update_checkbox(item, not current_val)
    
    def update_checkbox(self, item, value):
        """Actualiza el estado del checkbox"""
        values = list(self.station_tree.item(item, 'values'))
        values[0] = "✓" if value else ""
        self.station_tree.item(item, values=values)

    def log_message(self, message):
        """Muestra mensajes en la consola"""
        timestamp = UTCDateTime.now().strftime("%H:%M:%S")
        self.log_console.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_console.see(tk.END)
        self.log_console.update()

    def load_station_info(self):
        """Actualiza la información de las estaciones"""
        self.log_message("Actualizando información de estaciones...")
        self.status_var.set("Actualizando información...")
        
        try:
            # Limpiar datos anteriores
            for tree in [self.info_tree, self.station_tree]:
                for item in tree.get_children():
                    tree.delete(item)
            
            self.stations = []
            self.station_vars = {}
            
            # Obtener información del servidor
            cmd = ["slinktool", "-Q", self.server_host]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                self.log_message(f"Error: {result.stderr}")
                return
            
            # Procesar resultados
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 8:
                    net, sta, loc, chan = parts[0:4]
                    type_code, start_time = parts[4], " ".join(parts[5:7])
                    end_time = " ".join(parts[8:10]) if len(parts) >= 10 else "N/A"
                    
                    # Determinar estado
                    try:
                        end_dt = datetime.strptime(end_time, "%Y/%m/%d %H:%M:%S.%f") + timedelta(minutes=1)
                        status = "Activo" if end_dt >= datetime.now() else "Inactivo"
                    except:
                        status = "Desconocido"
                    
                    # Agregar a información completa
                    self.info_tree.insert('', 'end', values=(
                        net, sta, loc, chan, type_code, start_time, end_time, status
                    ))
                    
                    # Filtrar para panel izquierdo
                    if chan in ['EHZ', 'HNZ'] and status == "Activo":
                        self.stations.append((net, sta, chan))
                        station_key = f"{net}.{sta}"
                        self.station_vars[station_key] = False
                        self.station_tree.insert('', 'end', values=(
                            "", net, sta, chan, "No conectado"
                        ))
            
            self.log_message(f"Información actualizada. {len(self.stations)} estaciones activas.")
            self.status_var.set("Información actualizada")
            
        except Exception as e:
            self.log_message(f"Error al actualizar: {str(e)}")
            self.status_var.set("Error al actualizar")

    def send_to_application(self):
        """Envía las estaciones seleccionadas al graficador sísmico"""
        selected_stations = []
        for item in self.station_tree.get_children():
            values = self.station_tree.item(item, 'values')
            station_key = f"{values[1]}.{values[2]}"  # network.station
            if self.station_vars.get(station_key, False):
                selected_stations.append((values[1], values[2], "00", values[3]))  # (net, sta, loc, chan)
        
        if not selected_stations:
            self.log_message("No hay estaciones seleccionadas")
            return
        
        # Definir los paths de los StationXML (ajusta estas rutas según tu configuración)
        STATIONXML_PATHS = {
            "UIS09": "/home/jumavamu/Documentos/PruebasSeiscom/UIS09.xml",
            "UIS03": "/home/jumavamu/Documentos/PruebasSeiscom/UIS03.xml",
            "UIS05": "/home/jumavamu/Documentos/PruebasSeiscom/UIS05.xml",
            "UIS01": "/home/jumavamu/Documentos/PruebasSeiscom/UIS01.xml"   
        }
        
        # Filtrar solo los paths necesarios para las estaciones seleccionadas
        required_paths = {sta[1]: path for sta, path in STATIONXML_PATHS.items() 
                        if sta in [s[1] for s in selected_stations]}
        
        try:
            
            # Crear e iniciar el graficador
            plotter = SeismicPlotter(
                stations=selected_stations,
                stationxml_paths=required_paths,
                seedlink_host=self.server_host  # Usar el mismo servidor que el monitor
            )
            plotter.start()
            
            self.log_message(f"Iniciando graficador con {len(selected_stations)} estaciones")
            
        except ImportError:
            # Mostrar código para copiar y pegar si no se encuentra el módulo
            code = f"""# Configuración para el graficador
    stations = [
        {',\n    '.join([str(s) for s in selected_stations])}
    ]

    STATIONXML_PATHS = {{
        {',\n    '.join([f'"{sta}": "{path}"' for sta, path in required_paths.items()])}
    }}
    """
            self.show_code_dialog(code)
            self.log_message("Módulo graficador no encontrado. Se mostró código para copiar manualmente")
        except Exception as e:
            self.log_message(f"Error al iniciar el graficador: {str(e)}")

    def show_code_dialog(self, code):
        """Muestra el código generado"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Configuración para gráficos")
        dialog.geometry("700x400")
        
        ttk.Label(dialog, text="Copia esta configuración en tu aplicación de gráficos:").pack(pady=10)
        
        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, width=85, height=15)
        text.insert(tk.END, code)
        text.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Copiar", command=lambda: self.copy_to_clipboard(code)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cerrar", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def copy_to_clipboard(self, text):
        """Copia texto al portapapeles"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.log_message("Configuración copiada al portapapeles")

class SLClient(EasySeedLinkClient):
    def __init__(self, host, monitor):
        super().__init__(host)
        self.monitor = monitor
    
    def on_data(self, trace):
        """Maneja datos recibidos (simplificado)"""
        net, sta = trace.stats.network, trace.stats.station
        station_key = f"{net}.{sta}"
        
        if station_key in self.monitor.active_connections:
            self.monitor.active_connections[station_key]['last_received'] = UTCDateTime.now()
            self.monitor.active_connections[station_key]['packet_count'] += 1
            self.monitor.update_station_status(station_key, "Recibiendo datos")

if __name__ == "__main__":
    root = tk.Tk()
    # Estilo para el botón principal
    style = ttk.Style()
    style.configure('Accent.TButton', font=('Helvetica', 10, 'bold'), foreground='blue')
    
    app = SeedLinkMonitor(root)
    
    def on_closing():
        if app.running:
            app.stop_connection()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()