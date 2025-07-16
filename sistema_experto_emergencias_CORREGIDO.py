import streamlit as st
import osmnx as ox
import networkx as nx
import folium
import pandas as pd
import numpy as np
import random
import math
import datetime
import time
import json
import sqlite3
import os
from geopy.distance import geodesic
import streamlit.components.v1 as components

# Configuración de la página
st.set_page_config(
    page_title="Sistema Experto de Emergencias",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === SISTEMA DE BASE DE DATOS PARA INCIDENTES ===
def inicializar_base_datos():
    """Inicializa la base de datos SQLite para incidentes"""
    db_path = "incidentes_emergencia.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Crear tabla de incidentes si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nodo_incidente INTEGER NOT NULL,
            latitud REAL NOT NULL,
            longitud REAL NOT NULL,
            fecha_hora TEXT NOT NULL,
            patrulla_asignada TEXT,
            tipo_ruta TEXT,
            estado TEXT DEFAULT 'reportado',
            tiempo_respuesta INTEGER,
            fecha_resolucion TEXT,
            observaciones TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Crear tabla de historial de patrullas si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_patrullas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patrulla_id TEXT NOT NULL,
            incidente_id INTEGER,
            nodo_origen INTEGER,
            nodo_destino INTEGER,
            ruta_calculada TEXT,
            tipo_ruta TEXT,
            fecha_asignacion TEXT,
            fecha_confirmacion TEXT,
            fecha_inicio_movimiento TEXT,
            fecha_llegada TEXT,
            tiempo_total INTEGER,
            estado_final TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (incidente_id) REFERENCES incidentes (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    return db_path

def registrar_incidente(nodo, latitud, longitud, patrulla_asignada=None, tipo_ruta=None):
    """Registra un nuevo incidente en la base de datos"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    cursor = conn.cursor()
    
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT INTO incidentes (nodo_incidente, latitud, longitud, fecha_hora, patrulla_asignada, tipo_ruta, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (nodo, latitud, longitud, fecha_actual, patrulla_asignada, tipo_ruta, 'asignado' if patrulla_asignada else 'reportado'))
    
    incidente_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return incidente_id

def actualizar_estado_incidente(incidente_id, nuevo_estado, observaciones=None):
    """Actualiza el estado de un incidente"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    cursor = conn.cursor()
    
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if nuevo_estado == 'resuelto':
        cursor.execute('''
            UPDATE incidentes 
            SET estado = ?, fecha_resolucion = ?, observaciones = ?
            WHERE id = ?
        ''', (nuevo_estado, fecha_actual, observaciones, incidente_id))
    else:
        cursor.execute('''
            UPDATE incidentes 
            SET estado = ?, observaciones = ?
            WHERE id = ?
        ''', (nuevo_estado, observaciones, incidente_id))
    
    conn.commit()
    conn.close()

def registrar_mision_patrulla(patrulla_id, incidente_id, nodo_origen, nodo_destino, ruta_calculada, tipo_ruta):
    """Registra una misión de patrulla en el historial"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    cursor = conn.cursor()
    
    fecha_actual = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ruta_json = json.dumps(ruta_calculada) if ruta_calculada else None
    
    cursor.execute('''
        INSERT INTO historial_patrullas 
        (patrulla_id, incidente_id, nodo_origen, nodo_destino, ruta_calculada, tipo_ruta, fecha_asignacion, estado_final)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (patrulla_id, incidente_id, nodo_origen, nodo_destino, ruta_json, tipo_ruta, fecha_actual, 'asignado'))
    
    mision_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return mision_id

def obtener_incidentes_activos():
    """Obtiene todos los incidentes activos (no resueltos)"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    df = pd.read_sql_query('''
        SELECT * FROM incidentes 
        WHERE estado != 'resuelto' 
        ORDER BY fecha_hora DESC
    ''', conn)
    conn.close()
    return df

def obtener_historial_completo():
    """Obtiene el historial completo de incidentes y patrullas"""
    conn = sqlite3.connect("incidentes_emergencia.db")
    
    # Consulta con JOIN para obtener información completa
    df = pd.read_sql_query('''
        SELECT 
            i.id as incidente_id,
            i.nodo_incidente,
            i.latitud,
            i.longitud,
            i.fecha_hora as fecha_incidente,
            i.estado as estado_incidente,
            h.patrulla_id,
            h.tipo_ruta,
            h.fecha_asignacion,
            h.fecha_confirmacion,
            h.fecha_inicio_movimiento,
            h.fecha_llegada,
            h.tiempo_total,
            h.estado_final
        FROM incidentes i
        LEFT JOIN historial_patrullas h ON i.id = h.incidente_id
        ORDER BY i.fecha_hora DESC
    ''', conn)
    conn.close()
    return df

# Inicializar base de datos al cargar la aplicación
if 'db_initialized' not in st.session_state:
    inicializar_base_datos()
    st.session_state.db_initialized = True

# Título principal según especificaciones del proyecto
st.title("🚨 Sistema Experto de Soporte a la Decisión para Optimización de Rutas de Emergencia")
st.markdown("*Modelo de Costo Dual Dependiente del Tiempo - Tacna, Perú*")

# Obtener hora actual y nivel de tráfico dinámico
import pytz
timezone_peru = pytz.timezone('America/Lima')  # GMT-5
hora_actual = datetime.datetime.now(timezone_peru)
hora_formateada = hora_actual.strftime("%H:%M:%S - %d/%m/%Y")

def obtener_nivel_trafico(hora):
    """
    Determina el nivel de tráfico basado en la hora del día con 5 niveles granulares.
    """
    hora_num = hora.hour + hora.minute / 60.0
    
    if 6.5 <= hora_num < 8:  # 6:30 AM - 8:00 AM
        return "trafico_extremo", "🔴 Tráfico Extremo", "Hora pico escolar - máxima congestión"
    elif 8 <= hora_num < 11:  # 8:00 AM - 11:00 AM
        return "trafico_alto", "🟠 Tráfico Alto", "Mañana laboral - congestión alta"
    elif 11 <= hora_num < 13:  # 11:00 AM - 1:00 PM
        return "trafico_extremo", "🔴 Tráfico Extremo", "Mediodía - máxima congestión"
    elif 13 <= hora_num < 17:  # 1:00 PM - 5:00 PM
        return "trafico_medio", "🟡 Tráfico Medio", "Tarde laboral - congestión media"
    elif 17 <= hora_num < 20:  # 5:00 PM - 8:00 PM
        return "trafico_alto", "🟠 Tráfico Alto", "Hora pico vespertina - congestión alta"
    elif 20 <= hora_num < 23:  # 8:00 PM - 11:00 PM
        return "trafico_bajo", "🟢 Tráfico Bajo", "Noche temprana - poco tráfico"
    else:  # 11:00 PM - 6:30 AM
        return "trafico_minimo", "🟢 Tráfico Mínimo", "Madrugada - vías despejadas"

nivel_trafico, estado_trafico, descripcion_trafico = obtener_nivel_trafico(hora_actual)

# Mostrar información de estado de tráfico
col_estado1, col_estado2 = st.columns(2)
with col_estado1:
    st.warning(f"{estado_trafico}")
with col_estado2:
    st.markdown(f"**📋 Estado:** {descripcion_trafico}")

st.markdown("---")

# --- Funciones de Cache y Carga del Grafo ---
@st.cache_data
def cargar_grafo_tacna():
    """
    Carga un grafo enriquecido de Tacna con atributos estáticos para el modelo probabilístico.
    """
    try:
        place = "Tacna, Peru"
        # Crear grafo dirigido simplificado y fuertemente conectado
        G = ox.graph_from_place(place, network_type='drive', simplify=True)
        
        # Asegurar conectividad fuerte para evitar islas
        if not nx.is_strongly_connected(G):
            largest_scc = max(nx.strongly_connected_components(G), key=len)
            G = G.subgraph(largest_scc).copy()

        # Convertir a enteros para compatibilidad con JavaScript
        G = nx.convert_node_labels_to_integers(G, label_attribute='osmid')
        
        # Enriquecimiento del grafo con atributos estáticos
        for u, v, key, data in G.edges(data=True, keys=True):
            # Longitud del arco
            length = data.get('length', 100)
            
            # Clasificar tipo de vía basado en atributos OSM
            highway = data.get('highway', 'residential')
            if isinstance(highway, list):
                highway = highway[0]
            
            # Mapeo de tipos de vía según especificaciones
            if highway in ['primary', 'trunk', 'motorway']:
                tipo_via = 'avenida_principal'
                velocidad_base = 50
                sigma_base = 20
                factor_calidad = 1.2
            elif highway in ['secondary', 'tertiary']:
                tipo_via = 'calle_colectora'
                velocidad_base = 40
                sigma_base = 18
                factor_calidad = 1.3
            elif highway in ['residential', 'living_street']:
                tipo_via = 'calle_residencial'
                velocidad_base = 30
                sigma_base = 12
                factor_calidad = 1.1
            else:
                tipo_via = 'jiron_comercial'
                velocidad_base = 35
                sigma_base = 15
                factor_calidad = 1.4
            
            # Asignar atributos al arco
            G[u][v][key]['tipo_via'] = tipo_via
            G[u][v][key]['velocidad_base'] = velocidad_base
            G[u][v][key]['sigma_base'] = sigma_base
            G[u][v][key]['factor_calidad'] = factor_calidad
            G[u][v][key]['length'] = length

        st.success(f"✅ Grafo de Tacna cargado: {len(G.nodes)} nodos, {len(G.edges)} arcos")
        return G
        
    except Exception as e:
        st.error(f"❌ Error al cargar el grafo: {str(e)}")
        return None

# --- Interfaz de Usuario (Sidebar) ---
st.sidebar.header("⚙️ Panel de Control del Sistema Experto")
st.sidebar.markdown("**Configuración de Simulación**")

# Activación del modo de incidentes
modo_incidente_activo = st.sidebar.toggle(
    "🚨 Activar Modo Emergencia", 
    value=False,
    help="Permite reportar incidentes haciendo clic en el mapa"
)

# Factores dinámicos según especificaciones
st.sidebar.markdown("**Factores Dinámicos**")

# Mostrar el nivel de tráfico actual calculado automáticamente
st.sidebar.markdown(f"**Nivel de Tráfico Actual:**")
st.sidebar.markdown(f"{estado_trafico}")
st.sidebar.caption(f"{descripcion_trafico}")

# Opción manual para override del tráfico
usar_horario_manual = st.sidebar.checkbox(
    "🔧 Usar configuración manual de tráfico",
    value=False,
    help="Permite sobrescribir el nivel de tráfico automático"
)

if usar_horario_manual:
    nivel_trafico_manual = st.sidebar.selectbox(
        "Nivel de Tráfico (Manual):",
        options=['trafico_minimo', 'trafico_bajo', 'trafico_medio', 'trafico_alto', 'trafico_extremo'],
        index=2,
        help="Configuración manual de los 5 niveles de tráfico"
    )
    st.sidebar.warning("⚠️ Usando configuración manual")
    nivel_trafico_usado = nivel_trafico_manual
else:
    st.sidebar.success(f"✅ Usando tráfico automático: **{nivel_trafico}**")
    nivel_trafico_usado = nivel_trafico

# Condiciones climáticas incluyendo neblina
condicion_clima = st.sidebar.selectbox(
    "Condiciones Climáticas:",
    options=['despejado', 'lluvia', 'neblina'],
    help="Factor climático que afecta la velocidad en toda la red"
)

# Parámetro de riesgo k para el modelo de costo dual
st.sidebar.markdown("**Parámetros de Optimización**")
factor_riesgo_k = st.sidebar.slider(
    "Factor de Aversión al Riesgo (k):",
    min_value=0.0,
    max_value=3.0,
    value=1.5,
    step=0.1,
    help="Controla la importancia de la incertidumbre en la ruta segura: Costo_Seguro(e) = μ(e) + k×σ(e). k=0: solo tiempo esperado, k=3: muy conservador"
)

# Cargar grafo principal
G = cargar_grafo_tacna()

if G is not None:
    # Preparar datos del sistema
    nodes_list = list(G.nodes())
    num_patrullas = min(5, len(nodes_list))
    
    # Inicializar patrullas SOLO la primera vez o si no existen en session_state
    grafo_key = f"patrullas_{len(nodes_list)}_{num_patrullas}"
    
    if ('patrullas_data' not in st.session_state or 
        'patrullas_key' not in st.session_state or 
        st.session_state.patrullas_key != grafo_key):
        
        # Generar posiciones iniciales de patrullas
        patrol_nodes = random.sample(nodes_list, num_patrullas)
        
        # Crear datos de patrullas
        patrullas_data = []
        for i, node in enumerate(patrol_nodes):
            patrullas_data.append({
                'id': f"U-{i+1:02d}",
                'nodo_actual': int(node),
                'status': 'disponible'
            })
        
        # Guardar en session_state con clave de configuración
        st.session_state.patrullas_data = patrullas_data
        st.session_state.patrullas_key = grafo_key
    else:
        # Usar patrullas existentes del session_state
        patrullas_data = st.session_state.patrullas_data

    # Controles de gestión de patrullas
    st.sidebar.markdown("### 🚔 Gestión de Patrullas")
    
    # Mostrar estado actual de las patrullas
    patrullas_disponibles = [p for p in patrullas_data if p['status'] == 'disponible']
    patrullas_ocupadas = [p for p in patrullas_data if p['status'] != 'disponible']
    
    col_disp, col_ocup = st.sidebar.columns(2)
    with col_disp:
        st.metric("✅ Disponibles", len(patrullas_disponibles))
    with col_ocup:
        st.metric("🚫 Ocupadas", len(patrullas_ocupadas))
    
    # Botón para reinicializar patrullas manualmente
    if st.sidebar.button("🔄 Reinicializar Patrullas"):
        patrol_nodes = random.sample(nodes_list, num_patrullas)
        patrullas_data = []
        for i, node in enumerate(patrol_nodes):
            patrullas_data.append({
                'id': f"U-{i+1:02d}",
                'nodo_actual': int(node),
                'status': 'disponible'
            })
        st.session_state.patrullas_data = patrullas_data
        st.session_state.patrullas_key = grafo_key
        st.success("🔄 Patrullas reinicializadas correctamente")
        st.rerun()
    
    # Preparar datos de nodos para JavaScript
    nodes_data = {}
    for node, data in G.nodes(data=True):
        if 'y' in data and 'x' in data:
            nodes_data[int(node)] = {
                'lat': float(data['y']), 
                'lon': float(data['x'])
            }

    # Preparar datos de arcos con modelo de costo
    edges_data = []
    for u, v, key, data in G.edges(data=True, keys=True):
        if int(u) in nodes_data and int(v) in nodes_data:
            edges_data.append({
                'source': int(u), 
                'target': int(v),
                'length': float(data.get('length', 100)),
                'tipo_via': data.get('tipo_via', 'jiron_comercial'),
                'velocidad_base': float(data.get('velocidad_base', 30)),
                'sigma_base': float(data.get('sigma_base', 15)),
                'factor_calidad': float(data.get('factor_calidad', 1.4))
            })

    # Estado del sistema
    st.markdown("### 📊 Estado del Sistema")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🗺️ Nodos", len(nodes_data))
    with col2:
        st.metric("🛣️ Arcos", len(edges_data))
    with col3:
        st.metric("🚔 Patrullas", len(patrullas_data))
    with col4:
        patrullas_disponibles_count = len([p for p in patrullas_data if p['status'] == 'disponible'])
        delta_text = f"+{len(patrullas_data) - patrullas_disponibles_count} ocupadas" if patrullas_disponibles_count < len(patrullas_data) else "Todas disponibles"
        st.metric("✅ Disponibles", patrullas_disponibles_count, delta=delta_text)

    # Información del modo actual
    if modo_incidente_activo:
        st.success("🚨 **Modo Emergencia Activado:** Haga clic en el mapa para reportar un incidente")
    else:
        st.warning("⚠️ **Modo Emergencia Desactivado:** Active el interruptor en el panel lateral")

    # Controles del grafo
    mostrar_grafo = st.toggle(
        "🗺️ Mostrar Red Vial", 
        value=False,
        help="Visualiza todas las conexiones de calles en el mapa"
    )

    # Mapa de operaciones
    st.markdown("### 🗺️ Mapa de Operaciones")
    
    # Crear HTML del mapa con JavaScript completo
    mapa_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistema Experto de Emergencias</title>
        <meta charset="utf-8" />
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <style>
            #map {{ 
                height: 700px; 
                width: 100%; 
                cursor: {"crosshair" if modo_incidente_activo else "default"}; 
            }}
            .panel-recomendaciones {{
                position: absolute; 
                bottom: 10px; 
                right: 10px; 
                z-index: 1000;
                background: rgba(255, 255, 255, 0.98); 
                padding: 15px; 
                border-radius: 10px;
                box-shadow: 0 6px 20px rgba(0,0,0,0.25); 
                max-width: 480px; 
                max-height: 550px; 
                overflow-y: auto;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.4;
                border: 2px solid #007bff;
                transition: all 0.3s ease;
            }}
            .panel-recomendaciones.panel-minimized {{
                max-height: 60px;
                overflow: hidden;
            }}
            .panel-header {{
                display: flex; 
                justify-content: space-between; 
                align-items: center; 
                margin-bottom: 10px;
                border-bottom: 1px solid #dee2e6;
                padding-bottom: 8px;
            }}
            .panel-title {{
                margin: 0; 
                color: #007bff; 
                font-size: 1.1em;
                font-weight: bold;
            }}
            .panel-time {{
                font-size: 0.75em; 
                color: #6c757d;
                font-weight: normal;
            }}
            .btn-minimize {{
                background: none; 
                border: none; 
                font-size: 1.2em; 
                cursor: pointer; 
                color: #007bff;
                padding: 2px 6px;
                border-radius: 3px;
                transition: background-color 0.2s;
            }}
            .btn-minimize:hover {{
                background: #e3f2fd;
            }}
            .panel-content {{
                transition: opacity 0.3s ease;
            }}
            .panel-content.hidden {{
                opacity: 0;
                height: 0;
                overflow: hidden;
            }}
            .patrol-disponible {{
                background: linear-gradient(135deg, #28a745, #20c997); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid white; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            }}
            .patrol-ocupado {{
                background: linear-gradient(135deg, #6c757d, #495057); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid #adb5bd; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                opacity: 0.8;
            }}
            .patrol-asignado {{
                background: linear-gradient(135deg, #f39c12, #e67e22); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid white; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                animation: pulse 2s infinite;
            }}
            .patrol-en_ruta {{
                background: linear-gradient(135deg, #007bff, #0056b3); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid white; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                animation: move 3s ease-in-out infinite;
            }}
            .patrol-en_destino {{
                background: linear-gradient(135deg, #6f42c1, #e83e8c); 
                color: white; 
                border-radius: 50%;
                width: 32px; 
                height: 32px; 
                display: flex; 
                align-items: center; 
                justify-content: center;
                font-size: 11px; 
                font-weight: bold; 
                border: 2px solid white; 
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                animation: glow 2s ease-in-out infinite alternate;
            }}
            @keyframes pulse {{
                0% {{ transform: scale(1); }}
                50% {{ transform: scale(1.1); }}
                100% {{ transform: scale(1); }}
            }}
            @keyframes move {{
                0% {{ transform: translateX(0px); }}
                50% {{ transform: translateX(2px); }}
                100% {{ transform: translateX(0px); }}
            }}
            @keyframes glow {{
                0% {{ box-shadow: 0 2px 8px rgba(0,0,0,0.3); }}
                100% {{ box-shadow: 0 4px 16px rgba(111, 66, 193, 0.6); }}
            }}
        </style>
    </head>
    <body>
        <div id="map"></div>
        
        <div class="panel-recomendaciones" id="panel-recomendaciones">
            <div class="panel-header">
                <div style="display: flex; align-items: center;">
                    <h4 class="panel-title">🎯 Sistema Experto de Decisión</h4>
                    <span class="panel-time" id="panel-time">{hora_formateada}</span>
                </div>
                <button class="btn-minimize" onclick="togglePanel()" title="Minimizar/Maximizar Panel">
                    <span id="minimize-icon">−</span>
                </button>
            </div>
            <div class="panel-content" id="panel-content">
                <div id="contenido-recomendaciones">
                    <p style="color: #6c757d; font-style: italic;">
                        Esperando reporte de emergencia...
                    </p>
                    <small>Active el modo emergencia y haga clic en el mapa para comenzar.</small>
                </div>
            </div>
        </div>
        
        <script>
            // --- Configuración y Datos ---
            const MODO_EMERGENCIA = {str(modo_incidente_activo).lower()};
            const NIVEL_TRAFICO = "{nivel_trafico_usado}";
            const CONDICION_CLIMA = "{condicion_clima}";
            const FACTOR_RIESGO_K = {factor_riesgo_k};
            const MOSTRAR_GRAFO = {str(mostrar_grafo).lower()};
            const HORA_ACTUAL = "{hora_formateada}";

            const nodes = {json.dumps(nodes_data)};
            const edges = {json.dumps(edges_data)};
            const patrullas = {json.dumps(patrullas_data)};

            console.log(`Sistema inicializado: ${{Object.keys(nodes).length}} nodos, ${{edges.length}} arcos, ${{patrullas.length}} patrullas`);
            console.log(`Nivel de tráfico actual: ${{NIVEL_TRAFICO}} - Clima: ${{CONDICION_CLIMA}} a las ${{HORA_ACTUAL}}`);

            // --- Variables globales ---
            let panelMinimized = false;
            let marcadorIncidente, rutaRapidaLayer, rutaSeguraLayer, grafoLayer;
            let nodoDestino = null;
            let rutaRapida = null;
            let rutaSegura = null;

            // --- Función para Actualizar la Hora en el Panel ---
            function actualizarHoraPanel() {{
                const ahora = new Date();
                const horaFormateada = ahora.toLocaleString('es-PE', {{
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric'
                }});
                document.getElementById('panel-time').textContent = horaFormateada;
            }}

            // --- Función para Minimizar/Maximizar Panel ---
            window.togglePanel = function() {{
                const panel = document.getElementById('panel-recomendaciones');
                const content = document.getElementById('panel-content');
                const icon = document.getElementById('minimize-icon');
                
                panelMinimized = !panelMinimized;
                
                if (panelMinimized) {{
                    panel.classList.add('panel-minimized');
                    content.classList.add('hidden');
                    icon.textContent = '+';
                }} else {{
                    panel.classList.remove('panel-minimized');
                    content.classList.remove('hidden');
                    icon.textContent = '−';
                }}
            }}

            // --- Actualizar hora cada segundo ---
            setInterval(actualizarHoraPanel, 1000);
            
            // Actualizar hora inicial
            actualizarHoraPanel();

            // --- Inicialización del Mapa ---
            const map = L.map('map').setView([-18.0137, -70.2500], 14);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ 
                attribution: '© OpenStreetMap contributors',
                maxZoom: 18
            }}).addTo(map);

            // --- Visualización de Patrullas ---
            patrullas.forEach(p => {{
                const nodePos = nodes[p.nodo_actual];
                if (nodePos) {{
                    p.marker = L.marker([nodePos.lat, nodePos.lon], {{
                        icon: L.divIcon({{ 
                            html: `<div class="patrol-${{p.status}}">${{p.id}}</div>`, 
                            iconSize: [32, 32], 
                            className: '' 
                        }})
                    }}).addTo(map).bindPopup(
                        `<b>Patrulla ${{p.id}}</b><br>
                         Estado: <span style="font-weight: bold; color: green;">${{p.status}}</span><br>
                         <small>Nodo: ${{p.nodo_actual}}</small>`
                    );
                }}
            }});

            // --- Construcción de Lista de Adyacencia ---
            const listaAdyacencia = {{}};
            Object.keys(nodes).forEach(nodeId => {{
                listaAdyacencia[nodeId] = [];
            }});

            // Agregar aristas con modelo de costo
            edges.forEach(edge => {{
                const tiempoBase = edge.length / (edge.velocidad_base * 1000 / 3600);
                const costoRapido = tiempoBase * edge.factor_calidad;
                const costoSeguro = costoRapido * 1.2; // Ejemplo simplificado

                listaAdyacencia[edge.source].push({{
                    node: edge.target,
                    length: edge.length,
                    costo_rapido: costoRapido,
                    costo_seguro: costoSeguro,
                    tipo_via: edge.tipo_via
                }});
                
                listaAdyacencia[edge.target].push({{
                    node: edge.source,
                    length: edge.length,
                    costo_rapido: costoRapido,
                    costo_seguro: costoSeguro,
                    tipo_via: edge.tipo_via
                }});
            }});

            // --- Algoritmo A* simplificado ---
            function aStar(inicio, destino, tipoCosto) {{
                console.log(`🔍 A* iniciado: ${{inicio}} → ${{destino}} [${{tipoCosto}}]`);
                
                if (!nodes[inicio] || !nodes[destino]) {{
                    console.error(`❌ Nodos inválidos`);
                    return null;
                }}
                
                if (inicio === destino) {{
                    return {{ path: [inicio], cost: 0, nodesExplored: 1 }};
                }}

                // Heurística simple (distancia euclidiana)
                function heuristica(nodoA, nodoB) {{
                    const pA = nodes[nodoA];
                    const pB = nodes[nodoB];
                    if (!pA || !pB) return Infinity;
                    
                    const dx = pA.lat - pB.lat;
                    const dy = pA.lon - pB.lon;
                    return Math.sqrt(dx*dx + dy*dy) * 111000; // Aproximación en metros
                }}
                
                const openSet = new Set([inicio]);
                const closedSet = new Set();
                const cameFrom = new Map();
                const gScore = new Map([[inicio, 0]]);
                const fScore = new Map([[inicio, heuristica(inicio, destino)]]);
                
                let nodosExplorados = 0;
                const maxIteraciones = 2000;
                
                while (openSet.size > 0 && nodosExplorados < maxIteraciones) {{
                    let actual = null;
                    let menorF = Infinity;
                    for (let nodo of openSet) {{
                        const f = fScore.get(nodo) || Infinity;
                        if (f < menorF) {{
                            menorF = f;
                            actual = nodo;
                        }}
                    }}
                    
                    if (!actual) break;
                    
                    nodosExplorados++;
                    
                    if (actual === destino) {{
                        const ruta = [];
                        let temp = actual;
                        while (temp !== undefined) {{
                            ruta.unshift(temp);
                            temp = cameFrom.get(temp);
                        }}
                        console.log(`✅ Ruta encontrada: ${{ruta.length}} nodos`);
                        return {{ 
                            path: ruta, 
                            cost: gScore.get(destino), 
                            nodesExplored: nodosExplorados
                        }};
                    }}
                    
                    openSet.delete(actual);
                    closedSet.add(actual);
                    
                    const vecinos = listaAdyacencia[actual] || [];
                    for (let vecino of vecinos) {{
                        const nodoVecino = vecino.node;
                        
                        if (closedSet.has(nodoVecino)) continue;
                        
                        const costoTentativo = gScore.get(actual) + vecino[tipoCosto];
                        
                        const costoActual = gScore.get(nodoVecino);
                        if (costoActual === undefined || costoTentativo < costoActual) {{
                            cameFrom.set(nodoVecino, actual);
                            gScore.set(nodoVecino, costoTentativo);
                            fScore.set(nodoVecino, costoTentativo + heuristica(nodoVecino, destino));
                            
                            if (!openSet.has(nodoVecino)) {{
                                openSet.add(nodoVecino);
                            }}
                        }}
                    }}
                }}
                
                console.log(`❌ No se encontró ruta después de ${{nodosExplorados}} nodos`);
                return null;
            }}

            // --- Manejo de eventos de click en el mapa ---
            map.on('click', function(e) {{
                if (!MODO_EMERGENCIA) return;
                
                const coordsIncidente = e.latlng;
                console.log(`🚨 Emergencia reportada en: [${{coordsIncidente.lat.toFixed(6)}}, ${{coordsIncidente.lng.toFixed(6)}}]`);
                
                // Mostrar indicador de carga
                document.getElementById('contenido-recomendaciones').innerHTML = `
                    <div style="text-align: center; padding: 20px;">
                        <h5>🚨 Procesando Emergencia</h5>
                        <div style="margin: 15px 0;">
                            <div style="display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        </div>
                        <p>Calculando rutas óptimas...</p>
                        <style>
                            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                        </style>
                    </div>`;
                
                // Limpiar marcadores anteriores
                if (marcadorIncidente) map.removeLayer(marcadorIncidente);
                if (rutaRapidaLayer) map.removeLayer(rutaRapidaLayer);
                if (rutaSeguraLayer) map.removeLayer(rutaSeguraLayer);
                
                // Crear marcador de emergencia
                marcadorIncidente = L.marker(coordsIncidente, {{ 
                    icon: L.divIcon({{ 
                        html: '🚨', 
                        className: 'incident-marker', 
                        iconSize: [40, 40],
                        iconAnchor: [20, 20]
                    }}) 
                }}).addTo(map).bindPopup("<b>🚨 EMERGENCIA</b><br>Calculando respuesta óptima...").openPopup();
                
                setTimeout(() => {{
                    procesarEmergencia(coordsIncidente);
                }}, 100);
            }});
            
            // --- Función de procesamiento de emergencia ---
            function procesarEmergencia(coordsIncidente) {{
                try {{
                    // Encontrar nodo más cercano
                    nodoDestino = null;
                    let distanciaMinima = Infinity;
                    
                    Object.keys(nodes).forEach(nodeId => {{
                        const posNodo = L.latLng(nodes[nodeId].lat, nodes[nodeId].lon);
                        const distancia = posNodo.distanceTo(coordsIncidente);
                        if (distancia < distanciaMinima) {{
                            distanciaMinima = distancia;
                            nodoDestino = parseInt(nodeId);
                        }}
                    }});
                    
                    if (!nodoDestino) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: Ubicación no accesible</div>";
                        return;
                    }}
                    
                    console.log(`📍 Nodo destino: ${{nodoDestino}}, distancia: ${{distanciaMinima.toFixed(1)}}m`);
                    
                    // Registrar incidente en la base de datos
                    const incidenteData = {{
                        nodo: nodoDestino,
                        latitud: coordsIncidente.lat,
                        longitud: coordsIncidente.lng,
                        fecha_hora: new Date().toISOString()
                    }};
                    
                    // Evaluar patrullas disponibles
                    const patrullasDisponibles = patrullas.filter(p => p.status === 'disponible');
                    
                    if (patrullasDisponibles.length === 0) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>⚠️ No hay patrullas disponibles</div>";
                        return;
                    }}
                    
                    let candidatos = [];
                    
                    for (let p of patrullasDisponibles) {{
                        const resultado = aStar(p.nodo_actual, nodoDestino, 'costo_rapido');
                        
                        if (resultado && resultado.path && resultado.path.length > 0) {{
                            candidatos.push({{ 
                                patrulla: p, 
                                tiempo: resultado.cost,
                                nodosExplorados: resultado.nodesExplored
                            }});
                            console.log(`✅ Ruta para ${{p.id}}: ${{resultado.cost.toFixed(2)}}s`);
                        }} else {{
                            console.log(`❌ Sin ruta válida para ${{p.id}}`);
                        }}
                    }}
                    
                    if (candidatos.length === 0) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ No se encontró una ruta válida</div>";
                        return;
                    }}
                    
                    // Seleccionar mejor patrulla
                    candidatos.sort((a, b) => a.tiempo - b.tiempo);
                    const mejorPatrulla = candidatos[0].patrulla;
                    
                    console.log(`🏆 Mejor patrulla: ${{mejorPatrulla.id}} con tiempo: ${{candidatos[0].tiempo.toFixed(2)}}s`);
                    
                    setTimeout(() => {{
                        calcularRutasDuales(mejorPatrulla, nodoDestino);
                    }}, 100);
                    
                }} catch (error) {{
                    console.error('❌ Error en procesarEmergencia:', error);
                    document.getElementById('contenido-recomendaciones').innerHTML = 
                        `<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: ${{error.message}}</div>`;
                }}
            }}
            
            // --- Función para calcular rutas duales ---
            function calcularRutasDuales(mejorPatrulla, nodoDestino) {{
                try {{
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="text-align: center; padding: 15px;">
                            <h5>🎯 Calculando rutas para ${{mejorPatrulla.id}}</h5>
                            <p>Generando recomendaciones...</p>
                        </div>`;
                    
                    // Calcular ambas rutas
                    rutaRapida = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_rapido');
                    rutaSegura = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_seguro');
                    
                    if (!rutaRapida) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: No se pudo calcular la ruta</div>";
                        return;
                    }}
                    
                    function formatearTiempo(segundos) {{
                        if (!isFinite(segundos)) return "∞";
                        const mins = Math.floor(segundos / 60);
                        const segs = Math.round(segundos % 60);
                        return `${{mins}}:${{segs.toString().padStart(2, '0')}}`;
                    }}
                    
                    let htmlRecomendaciones = `<h5>🎯 Análisis para ${{mejorPatrulla.id}}</h5>`;
                    
                    // Visualizar ruta rápida
                    if (rutaRapida && rutaRapida.path) {{
                        const coordsRuta = rutaRapida.path.map(n => [nodes[n].lat, nodes[n].lon]);
                        rutaRapidaLayer = L.polyline(coordsRuta, {{ 
                            color: '#e74c3c', 
                            weight: 6, 
                            opacity: 0.9 
                        }}).addTo(map);
                        
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #e74c3c; padding: 12px; margin: 8px 0; background: #fff5f5; border-radius: 5px;">
                            <b>1. 🏃‍♂️ Ruta Rápida</b><br>
                            ⏱️ <b>Tiempo estimado:</b> ${{formatearTiempo(rutaRapida.cost)}}<br>
                            📍 <b>Nodos:</b> ${{rutaRapida.path.length}}<br>
                            🔍 <b>Explorados:</b> ${{rutaRapida.nodesExplored}}
                        </div>`;
                    }}
                    
                    // Visualizar ruta segura
                    if (rutaSegura && rutaSegura.path) {{
                        const coordsRuta = rutaSegura.path.map(n => [nodes[n].lat, nodes[n].lon]);
                        rutaSeguraLayer = L.polyline(coordsRuta, {{ 
                            color: '#3498db', 
                            weight: 6, 
                            opacity: 0.9,
                            dashArray: '15, 8'
                        }}).addTo(map);
                        
                        const diferenciaTiempo = rutaSegura.cost - rutaRapida.cost;
                        
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #3498db; padding: 12px; margin: 8px 0; background: #f0f8ff; border-radius: 5px;">
                            <b>2. 🛡️ Ruta Segura</b><br>
                            ⏱️ <b>Tiempo estimado:</b> ${{formatearTiempo(rutaSegura.cost)}}<br>
                            📍 <b>Nodos:</b> ${{rutaSegura.path.length}}<br>
                            📊 <b>Diferencia:</b> +${{formatearTiempo(diferenciaTiempo)}}
                        </div>`;
                    }}
                    
                    // Botones de asignación
                    htmlRecomendaciones += `
                    <div style="text-align: center; margin-top: 15px;">
                        <button onclick="asignarPatrulla('${{mejorPatrulla.id}}', 'rapida')" 
                                style="background: #e74c3c; color: white; border: none; padding: 10px 16px; margin: 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">
                            🏃‍♂️ Asignar Ruta Rápida
                        </button>
                        ${{rutaSegura ? `<button onclick="asignarPatrulla('${{mejorPatrulla.id}}', 'segura')" 
                                style="background: #3498db; color: white; border: none; padding: 10px 16px; margin: 5px; border-radius: 5px; cursor: pointer; font-weight: bold;">
                            🛡️ Asignar Ruta Segura
                        </button>` : ''}}
                    </div>`;
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = htmlRecomendaciones;
                    
                }} catch (error) {{
                    console.error('❌ Error en calcularRutasDuales:', error);
                    document.getElementById('contenido-recomendaciones').innerHTML = 
                        `<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: ${{error.message}}</div>`;
                }}
            }}

            // --- Función de asignación de patrulla CON MOVIMIENTO ---
            window.asignarPatrulla = function(idPatrulla, tipoRuta) {{
                console.log(`🚔 Asignando patrulla ${{idPatrulla}} con ruta ${{tipoRuta}}`);
                
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (patrulla) {{
                    // Cambiar estado inicial a "asignado"
                    patrulla.status = 'asignado';
                    patrulla.marker.setIcon(L.divIcon({{ 
                        html: `<div class="patrol-asignado">${{patrulla.id}}</div>`, 
                        iconSize: [32, 32], 
                        className: '' 
                    }}));
                    
                    const tipoTexto = tipoRuta === 'rapida' ? 'Rápida ⚡' : 'Segura 🛡️';
                    const rutaSeleccionada = tipoRuta === 'rapida' ? rutaRapida : rutaSegura;
                    
                    // Guardar información de la misión
                    patrulla.mision = {{
                        destino: nodoDestino,
                        tipoRuta: tipoRuta,
                        rutaCalculada: rutaSeleccionada ? rutaSeleccionada.path : [],
                        horaAsignacion: new Date(),
                        nodoActual: 0 // Índice en la ruta
                    }};
                    
                    // Guardar en localStorage para persistencia
                    const incidenteData = {{
                        id: Date.now(),
                        nodo_incidente: nodoDestino,
                        latitud: marcadorIncidente.getLatLng().lat,
                        longitud: marcadorIncidente.getLatLng().lng,
                        patrulla_asignada: idPatrulla,
                        tipo_ruta: tipoRuta,
                        ruta_calculada: rutaSeleccionada ? rutaSeleccionada.path : [],
                        fecha_hora: new Date().toISOString(),
                        estado: 'asignado'
                    }};
                    
                    // Guardar en localStorage
                    let incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
                    incidentes.push(incidenteData);
                    localStorage.setItem('incidentes_db', JSON.stringify(incidentes));
                    
                    console.log('💾 Incidente guardado en localStorage:', incidenteData);
                    
                    // Simular tiempo de confirmación del conductor (2-5 segundos)
                    const tiempoConfirmacion = 2000 + Math.random() * 3000;
                    console.log(`⏱️ Conductor responderá en ${{Math.round(tiempoConfirmacion/1000)}} segundos`);
                    
                    // Mostrar pantalla de espera
                    let tiempoRestante = Math.ceil(tiempoConfirmacion / 1000);
                    
                    const actualizarPantalla = () => {{
                        document.getElementById('contenido-recomendaciones').innerHTML = `
                            <div style="border: 2px solid #f39c12; background: #fff3cd; padding: 20px; border-radius: 10px; text-align: center;">
                                <h5 style="color: #856404;">📡 Esperando Confirmación del Conductor</h5>
                                <div style="margin: 15px 0;">
                                    <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #f39c12; border-top: 4px solid #fff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                                </div>
                                <p><strong>🚔 Patrulla:</strong> ${{patrulla.id}}</p>
                                <p><strong>📍 Ruta:</strong> ${{tipoTexto}}</p>
                                <p><strong>🎯 Destino:</strong> Nodo ${{nodoDestino}}</p>
                                <div style="background: #e67e22; color: white; padding: 10px; border-radius: 8px; margin: 15px 0; font-size: 1.2em; font-weight: bold;">
                                    ⏰ Confirmación en: ${{tiempoRestante}} segundos
                                </div>
                                <button onclick="confirmarInmediatamente('${{idPatrulla}}')" 
                                        style="background: #dc3545; color: white; border: none; padding: 10px 15px; margin-top: 10px; border-radius: 5px; cursor: pointer; font-size: 0.9em; font-weight: bold;">
                                    � CONFIRMAR INMEDIATAMENTE
                                </button>
                                <style>
                                    @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                                </style>
                            </div>`;
                    }};
                    
                    // Actualizar pantalla inicial
                    actualizarPantalla();
                    
                    // Countdown visual
                    const countdown = setInterval(() => {{
                        tiempoRestante--;
                        if (tiempoRestante > 0) {{
                            actualizarPantalla();
                        }} else {{
                            clearInterval(countdown);
                        }}
                    }}, 1000);
                    
                    // Timer para confirmación automática
                    patrulla.mision.timeoutConfirmacion = setTimeout(() => {{
                        console.log(`✅ Confirmación automática recibida de patrulla ${{idPatrulla}}`);
                        clearInterval(countdown);
                        iniciarMovimientoPatrulla(idPatrulla, incidenteData.id);
                    }}, tiempoConfirmacion);
                }}
            }}
            
            // --- Función para confirmar inmediatamente ---
            window.confirmarInmediatamente = function(idPatrulla) {{
                console.log(`🚨 CONFIRMACIÓN INMEDIATA para patrulla ${{idPatrulla}}`);
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (patrulla && patrulla.mision && patrulla.mision.timeoutConfirmacion) {{
                    clearTimeout(patrulla.mision.timeoutConfirmacion);
                    patrulla.mision.timeoutConfirmacion = null;
                    
                    // Buscar el ID del incidente para esta patrulla
                    const incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
                    const incidenteActivo = incidentes.find(inc => inc.patrulla_asignada === idPatrulla && inc.estado === 'asignado');
                    
                    iniciarMovimientoPatrulla(idPatrulla, incidenteActivo ? incidenteActivo.id : null);
                }}
            }}
            
            // --- Función para iniciar movimiento de patrulla ---
            function iniciarMovimientoPatrulla(idPatrulla, incidenteId) {{
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (!patrulla || !patrulla.mision || !patrulla.mision.rutaCalculada) {{
                    console.error(`❌ No se puede iniciar movimiento: datos de misión incompletos para ${{idPatrulla}}`);
                    return;
                }}
                
                const ruta = patrulla.mision.rutaCalculada;
                console.log(`🚀 Iniciando movimiento de ${{idPatrulla}} por ruta de ${{ruta.length}} nodos`);
                
                // Cambiar estado a en_ruta
                patrulla.status = 'en_ruta';
                patrulla.mision.horaInicio = new Date();
                patrulla.mision.nodoActual = 0;
                patrulla.mision.incidenteId = incidenteId;
                
                patrulla.marker.setIcon(L.divIcon({{ 
                    html: `<div class="patrol-en_ruta">${{patrulla.id}}</div>`, 
                    iconSize: [32, 32], 
                    className: '' 
                }}));
                
                // Mostrar panel de seguimiento
                mostrarPanelSeguimiento(patrulla);
                
                // Iniciar animación de movimiento
                animarMovimientoPatrulla(patrulla);
            }}
            
            // --- Función para mostrar panel de seguimiento ---
            function mostrarPanelSeguimiento(patrulla) {{
                const ruta = patrulla.mision.rutaCalculada;
                const tipoRuta = patrulla.mision.tipoRuta === 'rapida' ? 'Rápida ⚡' : 'Segura 🛡️';
                
                document.getElementById('contenido-recomendaciones').innerHTML = `
                    <div style="border: 2px solid #007bff; background: #e3f2fd; padding: 15px; border-radius: 10px;">
                        <h5 style="color: #0056b3;">🚀 Seguimiento en Tiempo Real</h5>
                        <div style="background: white; padding: 10px; border-radius: 5px; margin: 10px 0;">
                            <p><strong>🚔 Patrulla:</strong> ${{patrulla.id}}</p>
                            <p><strong>📍 Ruta:</strong> ${{tipoRuta}}</p>
                            <p><strong>🎯 Destino:</strong> Nodo ${{patrulla.mision.destino}}</p>
                            <p><strong>📊 Progreso:</strong> <span id="progreso-${{patrulla.id}}">0%</span></p>
                            <div style="background: #e9ecef; border-radius: 10px; height: 8px; margin: 5px 0;">
                                <div id="barra-progreso-${{patrulla.id}}" style="background: linear-gradient(90deg, #007bff, #0056b3); height: 100%; border-radius: 10px; width: 0%; transition: width 0.5s ease;"></div>
                            </div>
                            <p style="font-size: 0.9em;"><strong>🗺️ Posición actual:</strong> <span id="posicion-${{patrulla.id}}">Nodo ${{ruta[0]}}</span></p>
                            <p style="font-size: 0.9em;"><strong>⏱️ Tiempo transcurrido:</strong> <span id="tiempo-${{patrulla.id}}">00:00</span></p>
                        </div>
                        
                        <div style="text-align: center; margin-top: 10px;">
                            <button onclick="pausarMovimiento('${{patrulla.id}}')" 
                                    style="background: #ffc107; color: #212529; border: none; padding: 8px 12px; margin: 2px; border-radius: 4px; cursor: pointer; font-size: 0.9em;">
                                ⏸️ Pausar
                            </button>
                            <button onclick="acelerarMovimiento('${{patrulla.id}}')" 
                                    style="background: #17a2b8; color: white; border: none; padding: 8px 12px; margin: 2px; border-radius: 4px; cursor: pointer; font-size: 0.9em;">
                                ⚡ Acelerar
                            </button>
                            <button onclick="terminarMision('${{patrulla.id}}')" 
                                    style="background: #dc3545; color: white; border: none; padding: 8px 12px; margin: 2px; border-radius: 4px; cursor: pointer; font-size: 0.9em;">
                                🛑 Terminar
                            </button>
                        </div>
                    </div>`;
            }}
            
            // --- Función para animar movimiento de patrulla ---
            function animarMovimientoPatrulla(patrulla) {{
                if (!patrulla.mision || !patrulla.mision.rutaCalculada) {{
                    console.error(`❌ No se puede animar: datos incompletos para ${{patrulla.id}}`);
                    return;
                }}
                
                const ruta = patrulla.mision.rutaCalculada;
                console.log(`🎬 Iniciando animación de ${{patrulla.id}} por ruta: ${{ruta.join(' → ')}}`);
                
                patrulla.mision.animacionActiva = true;
                patrulla.mision.pausado = false;
                const velocidadBase = 2500; // 2.5 segundos por nodo (más lento)
                let velocidadActual = velocidadBase;
                
                // Función para mover al siguiente nodo
                const moverSiguienteNodo = () => {{
                    if (patrulla.mision.pausado || !patrulla.mision.animacionActiva) return;
                    
                    patrulla.mision.nodoActual++;
                    const indiceActual = patrulla.mision.nodoActual;
                    
                    // Verificar si llegó al destino
                    if (indiceActual >= ruta.length) {{
                        console.log(`🏁 ${{patrulla.id}} ha llegado al destino`);
                        completarMision(patrulla);
                        return;
                    }}
                    
                    // Obtener coordenadas del nuevo nodo
                    const nodoId = ruta[indiceActual];
                    const coordenadas = nodes[nodoId];
                    
                    if (coordenadas && coordenadas.lat && coordenadas.lon) {{
                        // Actualizar posición del marcador en el mapa
                        patrulla.marker.setLatLng([coordenadas.lat, coordenadas.lon]);
                        
                        // Actualizar datos de la patrulla
                        patrulla.nodo_actual = nodoId;
                        
                        // Actualizar panel de seguimiento
                        const progreso = Math.round((indiceActual / (ruta.length - 1)) * 100);
                        const tiempoTranscurrido = Math.floor((Date.now() - patrulla.mision.horaInicio) / 1000);
                        const minutos = Math.floor(tiempoTranscurrido / 60);
                        const segundos = tiempoTranscurrido % 60;
                        
                        // Actualizar elementos UI
                        const elementoProgreso = document.getElementById(`progreso-${{patrulla.id}}`);
                        const elementoBarra = document.getElementById(`barra-progreso-${{patrulla.id}}`);
                        const elementoPosicion = document.getElementById(`posicion-${{patrulla.id}}`);
                        const elementoTiempo = document.getElementById(`tiempo-${{patrulla.id}}`);
                        
                        if (elementoProgreso) elementoProgreso.textContent = `${{progreso}}%`;
                        if (elementoBarra) elementoBarra.style.width = `${{progreso}}%`;
                        if (elementoPosicion) elementoPosicion.textContent = `Nodo ${{nodoId}}`;
                        if (elementoTiempo) elementoTiempo.textContent = `${{minutos.toString().padStart(2, '0')}}:${{segundos.toString().padStart(2, '0')}}`;
                        
                        console.log(`📍 ${{patrulla.id}} movido al nodo ${{nodoId}} (${{progreso}}% completado)`);
                        
                        // Programar siguiente movimiento
                        patrulla.mision.timeoutMovimiento = setTimeout(moverSiguienteNodo, velocidadActual);
                    }} else {{
                        console.error(`❌ No se encontraron coordenadas para el nodo ${{nodoId}}`);
                        // Intentar con el siguiente nodo
                        patrulla.mision.timeoutMovimiento = setTimeout(moverSiguienteNodo, 100);
                    }}
                }};
                
                // Iniciar el primer movimiento
                console.log(`🎬 Comenzando animación de ${{patrulla.id}} en ${{velocidadActual}}ms por nodo`);
                patrulla.mision.timeoutMovimiento = setTimeout(moverSiguienteNodo, velocidadActual);
                
                // Funciones de control de movimiento
                window.pausarMovimiento = function(idPatrulla) {{
                    if (idPatrulla === patrulla.id) {{
                        patrulla.mision.pausado = !patrulla.mision.pausado;
                        const boton = event.target;
                        if (patrulla.mision.pausado) {{
                            boton.innerHTML = '▶️ Reanudar';
                            boton.style.background = '#28a745';
                            console.log(`⏸️ Movimiento de ${{idPatrulla}} pausado`);
                            if (patrulla.mision.timeoutMovimiento) {{
                                clearTimeout(patrulla.mision.timeoutMovimiento);
                            }}
                        }} else {{
                            boton.innerHTML = '⏸️ Pausar';
                            boton.style.background = '#ffc107';
                            console.log(`▶️ Movimiento de ${{idPatrulla}} reanudado`);
                            patrulla.mision.timeoutMovimiento = setTimeout(moverSiguienteNodo, velocidadActual);
                        }}
                    }}
                }};
                
                window.acelerarMovimiento = function(idPatrulla) {{
                    if (idPatrulla === patrulla.id) {{
                        velocidadActual = Math.max(500, velocidadActual * 0.5);
                        console.log(`⚡ Velocidad de ${{idPatrulla}} incrementada: ${{velocidadActual}}ms por nodo`);
                    }}
                }};
                
                window.terminarMision = function(idPatrulla) {{
                    if (idPatrulla === patrulla.id && confirm(`¿Terminar misión de ${{idPatrulla}}?`)) {{
                        patrulla.mision.animacionActiva = false;
                        if (patrulla.mision.timeoutMovimiento) {{                        clearTimeout(patrulla.mision.timeoutMovimiento);
                    }}
                    console.log(`🛑 Misión de ${{idPatrulla}} terminada manualmente`);
                    completarMision(patrulla);
                }}
            }};
        }}
        
        // --- Función para completar misión ---
        function completarMision(patrulla) {{
                const tiempoMision = Math.floor((Date.now() - patrulla.mision.horaInicio) / 1000);
                const minutos = Math.floor(tiempoMision / 60);
                const segundos = tiempoMision % 60;
                
                console.log(`✅ Misión completada por ${{patrulla.id}} en ${{minutos}}:${{segundos.toString().padStart(2, '0')}}`);
                
                // Limpiar timeouts
                if (patrulla.mision.timeoutMovimiento) {{
                    clearTimeout(patrulla.mision.timeoutMovimiento);
                }}
                
                // Guardar en base de datos
                const misionData = {{
                    id_patrulla: patrulla.id,
                    tipo_emergencia: patrulla.mision.tipoEmergencia,
                    prioridad: patrulla.mision.prioridad,
                    ubicacion: patrulla.mision.ubicacion,
                    tiempo_respuesta: tiempoMision,
                    distancia_recorrida: (patrulla.mision.rutaCalculada ? patrulla.mision.rutaCalculada.length : 0),
                    hora_inicio: new Date(patrulla.mision.horaInicio).toISOString(),
                    hora_fin: new Date().toISOString(),
                    estado: 'completada'
                }};
                
                fetch('/guardar_mision', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(misionData)
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.exito) {{
                        console.log(`💾 Misión de ${{patrulla.id}} guardada en BD con ID: ${{data.id_mision}}`);
                    }} else {{
                        console.error(`❌ Error guardando misión: ${{data.error}}`);
                    }}
                }})
                .catch(error => console.error('❌ Error de red guardando misión:', error));
                
                // Liberar patrulla
                liberarPatrulla(patrulla.id);
            }}
            
            // --- Función para liberar patrulla ---
            window.liberarPatrulla = function(idPatrulla, incidenteId) {{
                console.log(`🆓 Liberando patrulla ${{idPatrulla}} después de completar misión`);
                
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (patrulla) {{
                    // Limpiar animaciones y timeouts si existen
                    if (patrulla.mision && patrulla.mision.frameId) {{
                        cancelAnimationFrame(patrulla.mision.frameId);
                        patrulla.mision.frameId = null;
                    }}
                    if (patrulla.mision && patrulla.mision.timeoutMovimiento) {{
                        clearTimeout(patrulla.mision.timeoutMovimiento);
                    }}
                    if (patrulla.mision && patrulla.mision.timeoutConfirmacion) {{
                        clearTimeout(patrulla.mision.timeoutConfirmacion);
                    }}
                    
                    // Cambiar estado a disponible
                    patrulla.status = 'disponible';
                    patrulla.marker.setIcon(L.divIcon({{ 
                        html: `<div class="patrol-disponible">${{patrulla.id}}</div>`, 
                        iconSize: [32, 32], 
                        className: '' 
                    }}));
                    
                    // Actualizar incidente en localStorage
                    if (incidenteId) {{
                        let incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
                        const incidenteIndex = incidentes.findIndex(inc => inc.id === incidenteId);
                        if (incidenteIndex !== -1) {{
                            incidentes[incidenteIndex].estado = 'resuelto';
                            incidentes[incidenteIndex].fecha_resolucion = new Date().toISOString();
                            incidentes[incidenteIndex].tiempo_total = patrulla.mision && patrulla.mision.horaInicio ? 
                                Math.floor((Date.now() - patrulla.mision.horaInicio) / 1000) : 0;
                            incidentes[incidenteIndex].distancia_recorrida = patrulla.mision && patrulla.mision.distanciaTotal ? 
                                patrulla.mision.distanciaTotal : 0;
                            incidentes[incidenteIndex].velocidad_promedio = patrulla.mision && patrulla.mision.distanciaTotal && patrulla.mision.horaInicio ? 
                                ((patrulla.mision.distanciaTotal / Math.floor((Date.now() - patrulla.mision.horaInicio) / 1000)) * 3.6).toFixed(1) : 0;
                            localStorage.setItem('incidentes_db', JSON.stringify(incidentes));
                            console.log('💾 Incidente marcado como resuelto con estadísticas completas:', incidenteId);
                        }}
                    }}
                    
                    // Limpiar datos de misión
                    patrulla.mision = null;
                    
                    // Limpiar marcador de incidente si existe
                    if (marcadorIncidente) {{
                        map.removeLayer(marcadorIncidente);
                        marcadorIncidente = null;
                    }}
                    
                    // Limpiar rutas mostradas
                    if (rutaRapidaLayer) {{
                        map.removeLayer(rutaRapidaLayer);
                        rutaRapidaLayer = null;
                    }}
                    if (rutaSeguraLayer) {{
                        map.removeLayer(rutaSeguraLayer);
                        rutaSeguraLayer = null;
                    }}
                    
                    // Mostrar mensaje de éxito
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="border: 2px solid #17a2b8; background: #d1ecf1; padding: 20px; border-radius: 10px; text-align: center;">
                            <h5 style="color: #0c5460;">🎉 ¡Misión Finalizada!</h5>
                            <div style="background: white; padding: 15px; border-radius: 8px; margin: 15px 0;">
                                <p><strong>✅ Patrulla ${{patrulla.id}} liberada exitosamente</strong></p>
                                <p><strong>🔄 Estado:</strong> Disponible para nuevas misiones</p>
                                <p><strong>💾 Incidente:</strong> Registrado y completado con estadísticas</p>
                                <p><strong>🚗 Animación:</strong> Movimiento suave finalizado</p>
                            </div>
                            <div style="color: #0c5460; font-size: 0.9em; margin-top: 10px;">
                                💡 Puedes reportar un nuevo incidente haciendo clic en el mapa
                            </div>
                        </div>`;
                    
                    // Reiniciar variables globales
                    nodoDestino = null;
                    rutaRapida = null;
                    rutaSegura = null;
                    
                    console.log(`✅ Patrulla ${{idPatrulla}} liberada y disponible para nuevas misiones`);
                }}
            }}
            
            // --- Función para mostrar incidentes guardados ---
            window.mostrarIncidentesGuardados = function() {{
                const incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
                console.log('📊 Incidentes en localStorage:', incidentes);
                
                if (incidentes.length === 0) {{
                    console.log('📝 No hay incidentes registrados');
                    return;
                }}
                
                console.log('📋 Resumen de incidentes:');
                incidentes.forEach((inc, index) => {{
                    console.log(`  ${{index + 1}}. ID: ${{inc.id}} - Patrulla: ${{inc.patrulla_asignada}} - Estado: ${{inc.estado}} - Fecha: ${{new Date(inc.fecha_hora).toLocaleString()}}`);
                }});
                
                const activos = incidentes.filter(inc => inc.estado !== 'resuelto');
                const resueltos = incidentes.filter(inc => inc.estado === 'resuelto');
                
                console.log(`📊 Estadísticas: ${{activos.length}} activos, ${{resueltos.length}} resueltos`);
            }}
            
            // --- Función para limpiar datos ---
            window.limpiarIncidentesGuardados = function() {{
                localStorage.removeItem('incidentes_db');
                console.log('🗑️ Incidentes eliminados de localStorage');
            }}

            console.log('🎮 Sistema de emergencias cargado correctamente');
            
            // --- Funciones de Debug Globales ---
            window.debug = {{
                patrullas: patrullas,
                nodes: nodes,
                edges: edges,
                mostrarIncidentes: mostrarIncidentesGuardados,
                limpiarIncidentes: limpiarIncidentesGuardados,
                asignar: window.asignarPatrulla,
                liberar: window.liberarPatrulla
            }};
            
            console.log('🔧 Funciones de debug disponibles en window.debug');
            console.log('📝 Comandos útiles:');
            console.log('  - debug.mostrarIncidentes() // Ver incidentes guardados');
            console.log('  - debug.limpiarIncidentes() // Limpiar localStorage');
            console.log('  - debug.patrullas // Ver estado de patrullas');
        </script>
    </body>
    </html>
    """
    
    # Mostrar el mapa
    components.html(mapa_html, height=750)

    # Mostrar base de datos de incidentes
    st.markdown("### 📊 Base de Datos de Incidentes")
    
    # Botones de control de la base de datos
    col_db1, col_db2, col_db3 = st.columns(3)
    
    with col_db1:
        if st.button("🔄 Actualizar desde localStorage"):
            components.html("""
            <script>
            const incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
            console.log('🔄 Sincronizando incidentes desde localStorage:', incidentes.length);
            
            // Enviar datos a Streamlit mediante un mecanismo de comunicación
            if (incidentes.length > 0) {
                // Guardar en un elemento oculto para que Streamlit pueda leerlo
                const hiddenDiv = document.createElement('div');
                hiddenDiv.id = 'incidentes-data';
                hiddenDiv.style.display = 'none';
                hiddenDiv.textContent = JSON.stringify(incidentes);
                document.body.appendChild(hiddenDiv);
                
                console.log('📤 Datos preparados para Streamlit');
            }
            </script>
            """, height=0)
            st.info("📊 Datos actualizados desde el navegador")
    
    with col_db2:
        if st.button("🗑️ Limpiar localStorage"):
            components.html("""
            <script>
            localStorage.removeItem('incidentes_db');
            console.log('🗑️ localStorage limpiado');
            </script>
            """, height=0)
            st.success("🗑️ Datos locales eliminados")
    
    with col_db3:
        if st.button("📊 Mostrar en Consola"):
            components.html("""
            <script>
            if (typeof mostrarIncidentesGuardados === 'function') {
                mostrarIncidentesGuardados();
            } else {
                const incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
                console.log('📊 Incidentes en localStorage:', incidentes);
            }
            </script>
            """, height=0)
            st.info("📊 Datos mostrados en consola (F12)")
    
    # Pestañas para organizar la información
    tab1, tab2, tab3 = st.tabs(["🚨 Incidentes Activos", "📋 Historial Completo", "📈 Estadísticas"])
    
    with tab1:
        incidentes_activos = obtener_incidentes_activos()
        if not incidentes_activos.empty:
            st.dataframe(incidentes_activos, use_container_width=True)
            st.info(f"📊 Se muestran {len(incidentes_activos)} incidentes activos de la base de datos SQL")
        else:
            st.info("No hay incidentes activos en la base de datos SQL. Los datos del navegador se guardan en localStorage.")
            
            # Mostrar información sobre localStorage
            st.markdown("""
            **💡 Información sobre el almacenamiento:**
            - Los incidentes se guardan temporalmente en localStorage del navegador
            - Use el botón "🔄 Actualizar desde localStorage" para sincronizar
            - Los datos persisten durante la sesión del navegador
            - Para un almacenamiento permanente, se requiere integración con backend
            """)
    
    with tab2:
        historial_completo = obtener_historial_completo()
        if not historial_completo.empty:
            st.dataframe(historial_completo, use_container_width=True)
        else:
            st.info("No hay historial de incidentes en la base de datos SQL.")
            
            # Agregar información sobre cómo funciona el sistema
            st.markdown("""
            **🔧 Funcionamiento del Sistema:**
            
            1. **Registro Temporal:** Los incidentes se guardan primero en localStorage del navegador
            2. **Persistencia:** Para guardar permanentemente, se requiere sincronización manual
            3. **Base de Datos:** SQLite está configurado pero requiere integración completa
            4. **Desarrollo:** Este es un prototipo funcional con almacenamiento temporal
            
            **🎮 Para probar el sistema:**
            - Active el modo emergencia
            - Haga clic en el mapa para reportar un incidente
            - Asigne una patrulla usando los botones del panel
            - Complete la misión liberando la patrulla
            - Use F12 para ver los logs en la consola del navegador
            """)
    
    with tab3:
        incidentes_activos = obtener_incidentes_activos()
        historial_completo = obtener_historial_completo()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🚨 Incidentes Activos (SQL)", len(incidentes_activos))
        with col2:
            st.metric("📋 Total Registrados (SQL)", len(historial_completo))
        with col3:
            patrullas_en_mision = len([p for p in patrullas_data if p['status'] != 'disponible'])
            st.metric("🚔 Patrullas en Misión", patrullas_en_mision)
        with col4:
            if not historial_completo.empty:
                tiempo_promedio = historial_completo['tiempo_total'].mean() if 'tiempo_total' in historial_completo.columns else 0
                st.metric("⏱️ Tiempo Promedio", f"{tiempo_promedio:.1f}s")
            else:
                st.metric("⏱️ Tiempo Promedio", "N/A")
        
        # Información adicional sobre el estado del sistema
        st.markdown("### 📊 Estado del Sistema en Tiempo Real")
        
        # Mostrar información sobre localStorage
        components.html("""
        <div style="padding: 15px; background: #f8f9fa; border-radius: 8px; margin: 10px 0;">
            <h6>💾 Datos en Navegador (localStorage)</h6>
            <div id="localStorage-stats">
                <p>Cargando estadísticas...</p>
            </div>
        </div>
        
        <script>
        function actualizarEstadisticasLocalStorage() {
            const incidentes = JSON.parse(localStorage.getItem('incidentes_db') || '[]');
            const activos = incidentes.filter(inc => inc.estado !== 'resuelto');
            const resueltos = incidentes.filter(inc => inc.estado === 'resuelto');
            
            const statsDiv = document.getElementById('localStorage-stats');
            if (statsDiv) {
                statsDiv.innerHTML = `
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <div><strong>📊 Total incidentes:</strong> ${incidentes.length}</div>
                        <div><strong>🔴 Activos:</strong> ${activos.length}</div>
                        <div><strong>✅ Resueltos:</strong> ${resueltos.length}</div>
                        <div><strong>🕐 Última actualización:</strong> ${new Date().toLocaleTimeString()}</div>
                    </div>
                    <div style="margin-top: 10px;">
                        <small style="color: #6c757d;">
                            Abra la consola del navegador (F12) y ejecute <code>mostrarIncidentesGuardados()</code> para ver detalles
                        </small>
                    </div>
                `;
            }
        }
        
        // Actualizar estadísticas cada 5 segundos
        actualizarEstadisticasLocalStorage();
        setInterval(actualizarEstadisticasLocalStorage, 5000);
        </script>
        """, height=120)

    # JavaScript para manejar la comunicación con el mapa
    components.html("""
    <script>
    window.addEventListener('message', function(event) {
        if (event.data.type === 'registrar_incidente') {
            console.log('📝 Registrando incidente en base de datos:', event.data.data);
            // En una implementación real, aquí se haría la llamada al backend
            // Por ahora solo mostramos el log
        }
    });
    </script>
    """, height=0)

else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifique la conexión a internet y reinicie la aplicación.")
    st.info("💡 **Sugerencia:** Asegúrese de tener una conexión estable a internet para descargar los datos de OpenStreetMap.")
