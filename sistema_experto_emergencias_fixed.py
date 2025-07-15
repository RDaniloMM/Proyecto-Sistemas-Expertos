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
from geopy.distance import geodesic
import streamlit.components.v1 as components

# Configuración de la página
st.set_page_config(
    page_title="Sistema Experto de Emergencias",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título principal según especificaciones del proyecto
st.title("🚨 Sistema Experto de Soporte a la Decisión para Optimización de Rutas de Emergencia")
st.markdown("*Modelo de Costo Dual Dependiente del Tiempo - Tacna, Perú*")

# Obtener hora actual y nivel de tráfico dinámico
hora_actual = datetime.datetime.now()
hora_formateada = hora_actual.strftime("%H:%M:%S - %d/%m/%Y")

def obtener_nivel_trafico(hora):
    """
    Determina el nivel de tráfico basado en la hora del día con 5 niveles granulares.
    """
    hora_num = hora.hour + hora.minute / 60.0
    
    if 6.5 <= hora_num < 8:  # 6:30 AM - 8:00 AM
        return "trafico_extremo", "🔴 Tráfico Extremo", "Hora pico escolar - máxima congestión"
    elif 8 <= hora_num < 11:  # 8:00 AM - 11:00 AM
        return "trafico_alto", "� Tráfico Alto", "Mañana laboral - congestión alta"
    elif 11 <= hora_num < 13:  # 11:00 AM - 1:00 PM
        return "trafico_extremo", "🔴 Tráfico Extremo", "Mediodía - máxima congestión"
    elif 13 <= hora_num < 17:  # 1:00 PM - 5:00 PM
        return "trafico_medio", "🟡 Tráfico Medio", "Tarde laboral - congestión media"
    elif 17 <= hora_num < 20:  # 5:00 PM - 8:00 PM
        return "trafico_alto", "� Tráfico Alto", "Hora pico vespertina - congestión alta"
    elif 20 <= hora_num < 23:  # 8:00 PM - 11:00 PM
        return "trafico_bajo", "🟢 Tráfico Bajo", "Noche temprana - poco tráfico"
    else:  # 11:00 PM - 6:30 AM
        return "trafico_minimo", "🟢 Tráfico Mínimo", "Madrugada - vías despejadas"

def obtener_factores_trafico():
    """
    Retorna los factores de penalización por nivel de tráfico y tipo de vía.
    """
    return {
        "trafico_minimo": {
            "avenida": 0.7, "jiron": 0.8, "colectora": 0.9, "residencial": 1.0
        },
        "trafico_bajo": {
            "avenida": 1.0, "jiron": 1.1, "colectora": 1.0, "residencial": 1.0
        },
        "trafico_medio": {
            "avenida": 1.5, "jiron": 1.3, "colectora": 1.2, "residencial": 1.1
        },
        "trafico_alto": {
            "avenida": 2.2, "jiron": 1.8, "colectora": 1.5, "residencial": 1.2
        },
        "trafico_extremo": {
            "avenida": 3.0, "jiron": 2.5, "colectora": 2.0, "residencial": 1.3
        }
    }

def obtener_factores_zona_especial():
    """
    Retorna factores de penalización para zonas especiales según especificaciones del proyecto.
    """
    return {
        "mercado": {"min": 1.70, "max": 2.50, "descripcion": "Mercados y zonas comerciales"},
        "paradero": {"min": 1.40, "max": 1.60, "descripcion": "Paraderos informales en avenidas"},
        "centro_historico": {"min": 1.30, "max": 1.50, "descripcion": "Calles angostas del centro histórico"},
        "zona_escolar": {"min": 2.00, "max": 3.50, "descripcion": "Zonas escolares (horas pico)"},
        "via_mala": {"min": 1.80, "max": 3.00, "descripcion": "Vías no asfaltadas o en mal estado"},
        "hospital": {"min": 1.25, "max": 1.40, "descripcion": "Alrededores de hospitales y clínicas"},
        "cruce_sin_semaforo": {"min": 1.30, "max": 1.70, "descripcion": "Cruces sin semáforo"}
    }

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

# Información del modelo
st.sidebar.markdown("**Información del Modelo**")
st.sidebar.info(f"""
**Funciones de Costo Probabilístico:**
- 🏃‍♂️ Rápida: Costo(e) = μ(e)
- 🛡️ Segura: Costo(e) = μ(e) + k×σ(e)

**Donde:**
- μ(e) = tiempo esperado con todos los factores dinámicos
- σ(e) = incertidumbre/volatilidad dependiente del tipo de vía
- k = {factor_riesgo_k} (factor de aversión al riesgo ajustable)

**Sistema de Tráfico Granular (5 niveles):**
- 🟢 Tráfico Mínimo: Avenidas 0.7×, Jirones 0.8×
- 🟢 Tráfico Bajo: Avenidas 1.0×, Jirones 1.1×  
- 🟡 Tráfico Medio: Avenidas 1.5×, Jirones 1.3×
- 🟠 Tráfico Alto: Avenidas 2.2×, Jirones 1.8×
- 🔴 Tráfico Extremo: Avenidas 3.0×, Jirones 2.5×

**Factores de Incertidumbre (σ base):**
- Avenidas: 0.4 (MUY VARIABLES)
- Jirones comerciales: 0.35 (VARIABLES)
- Colectoras: 0.25 (ALGO VARIABLES)
- Residenciales: 0.15 (ESTABLES)

**Multiplicadores de Incertidumbre:**
- 🌧️ Lluvia: ×1.8 en σ(e)
- 🌫️ Neblina: ×1.6 en σ(e)
- 🔴 Tráfico extremo: ×2.0 en σ(e)
- 🏪 Zonas especiales: +80% de penalización a σ(e)

**Zonas Especiales (según proyecto):**
- 🏪 Mercados: 1.7× - 2.5× (horas comerciales)
- 🚌 Paraderos informales: 1.4× - 1.6× (constante)
- 🏛️ Centro histórico: 1.3× - 1.5× (calles angostas)
- 🏫 Zonas escolares: 2.0× - 3.5× (horas pico)
- 🛣️ Vías en mal estado: 1.8× - 3.0× (permanente)
- 🏥 Hospitales: 1.25× - 1.4× (congestión)
- ⚠️ Cruces sin semáforo: 1.3× - 1.7× (variable)

**Nivel Actual:** {estado_trafico}
**Clima:** {condicion_clima.title()}
**Factor k actual:** {factor_riesgo_k} ({'Conservador' if factor_riesgo_k > 2.0 else 'Moderado' if factor_riesgo_k > 1.0 else 'Agresivo'})
""")

# Cargar grafo principal
G = cargar_grafo_tacna()

if G is not None:
    # Preparar datos del sistema
    nodes_list = list(G.nodes())
    num_patrullas = min(5, len(nodes_list))
    patrol_nodes = random.sample(nodes_list, num_patrullas)

    # Información de patrullas con estado
    patrullas_data = []
    for i, node in enumerate(patrol_nodes):
        patrullas_data.append({
            'id': f"U-{i+1:02d}",
            'nodo_actual': int(node),
            'status': 'disponible'
        })

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
        patrullas_disponibles = len([p for p in patrullas_data if p['status'] == 'disponible'])
        st.metric("✅ Disponibles", patrullas_disponibles)

    # Información del modo actual
    if modo_incidente_activo:
        st.success("🚨 **Modo Emergencia Activado:** Haga clic en el mapa para reportar un incidente")
    else:
        st.warning("⚠️ **Modo Emergencia Desactivado:** Active el interruptor en el panel lateral")

    # Información del modelo (movida arriba del mapa)
    st.markdown("### 📈 Información del Modelo")
    col_info1, col_info2 = st.columns(2)
    
    with col_info1:
        st.markdown(f"""
        **⚡ Modelo Probabilístico de Costo Dual:**
        - Ruta Rápida: `Costo(e) = μ(e)`
        - Ruta Segura: `Costo(e) = μ(e) + k×σ(e)`
        - **μ(e):** Tiempo esperado con factores dinámicos
        - **σ(e):** Incertidumbre por tipo de vía y condiciones
        - **k = {factor_riesgo_k}:** Factor de aversión al riesgo
        - **🕐 Tráfico dinámico:** {estado_trafico}
        - **🌤️ Condición climática:** {condicion_clima.title()}
        
        **🛡️ Factores de Incertidumbre (σ base):**
        - Avenidas: **0.4** (muy variables)
        - Jirones: **0.35** (variables)  
        - Colectoras: **0.25** (algo variables)
        - Residenciales: **0.15** (estables)
        """)
    
    with col_info2:
        st.markdown(f"""
        **📊 Sistema de Tráfico Granular (5 Niveles):**
        - 🟢 **Mínimo:** Avenidas 0.7×, Jirones 0.8×
        - 🟢 **Bajo:** Avenidas 1.0×, Jirones 1.1×
        - 🟡 **Medio:** Avenidas 1.5×, Jirones 1.3×
        - 🟠 **Alto:** Avenidas 2.2×, Jirones 1.8×
        - 🔴 **Extremo:** Avenidas 3.0×, Jirones 2.5×
        
        **🌦️ Multiplicadores de Incertidumbre:**
        - ☀️ Despejado: Sin multiplicador
        - 🌧️ Lluvia: ×1.8 en σ(e)
        - 🌫️ Neblina: ×1.6 en σ(e)
        - 🔴 Tráfico extremo: ×2.0 en σ(e)
        
        **� Factor k = {factor_riesgo_k}:**
        {'🔴 Muy Conservador' if factor_riesgo_k > 2.5 else '🟠 Conservador' if factor_riesgo_k > 2.0 else '🟡 Moderado' if factor_riesgo_k > 1.0 else '🟢 Agresivo'}
        """)
    
    # Mostrar factores actuales aplicados
    st.info(f"""
    **🎯 Factores Actuales Aplicados:**
    • **Nivel de tráfico:** {nivel_trafico_usado.replace('_', ' ').title()}
    • **Condición climática:** {condicion_clima.title()}
    • **Nivel de aversión al riesgo:** k = {factor_riesgo_k} ({'Muy Conservador' if factor_riesgo_k > 2.5 else 'Conservador' if factor_riesgo_k > 2.0 else 'Moderado' if factor_riesgo_k > 1.0 else 'Agresivo'})
    • **Modelo probabilístico:** μ(e) + k×σ(e) activo para ruta segura
    • **Todas las zonas especiales:** Activas con simulación probabilística
    """)

    # Controles del grafo (movidos arriba del mapa)
    st.markdown("### 🗺️ Controles de Visualización")
    
    col_control1, col_control2 = st.columns([1, 2])
    
    with col_control1:
        mostrar_grafo = st.toggle(
            "🗺️ Mostrar Red Vial", 
            value=False,
            help="Visualiza todas las conexiones de calles en el mapa"
        )
    
    with col_control2:
        if mostrar_grafo:
            st.info(f"""
            **📊 Red Vial Completa:**
            🛣️ **{len(edges_data)}** conexiones viales
            🏛️ **{len(nodes_data)}** intersecciones
            
            **Leyenda de Colores:**
            🟠 Avenidas principales  
            🟣 Calles colectoras  
            🟢 Calles residenciales  
            🔵 Jirones comerciales  
            ⚫ Otros tipos
            """)
        else:
            st.markdown("""
            **Controles disponibles:**
            - ✅ Activar visualización de red
            - 🎯 Ver estadísticas de conectividad
            - 🛣️ Análisis de tipos de vía
            """)

    # Mapa de operaciones
    st.markdown("### 🗺️ Mapa de Operaciones")
    
    # Crear HTML del mapa
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
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                border: 2px solid #3498db;
                transition: all 0.3s ease;
            }}
            .panel-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                padding-bottom: 8px;
                border-bottom: 2px solid #e8f4f8;
            }}
            .panel-title {{
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin: 0;
            }}
            .panel-time {{
                font-size: 11px;
                color: #7f8c8d;
                font-family: 'Courier New', monospace;
                background: #ecf0f1;
                padding: 3px 6px;
                border-radius: 4px;
                margin-left: 8px;
            }}
            .btn-minimize {{
                background: #e74c3c;
                color: white;
                border: none;
                border-radius: 50%;
                width: 25px;
                height: 25px;
                font-size: 12px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s ease;
                font-weight: bold;
            }}
            .btn-minimize:hover {{
                background: #c0392b;
                transform: scale(1.1);
            }}
            .panel-minimized {{
                max-height: 60px;
                overflow: hidden;
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

            // --- Variables para el Panel ---
            let panelMinimized = false;

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
                    console.log('📦 Panel minimizado');
                }} else {{
                    panel.classList.remove('panel-minimized');
                    content.classList.remove('hidden');
                    icon.textContent = '−';
                    console.log('📤 Panel maximizado');
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
                         Estado: <span id="status-${{p.id}}">${{p.status}}</span><br>
                         <small>Nodo: ${{p.nodo_actual}}</small>`
                    );
                }}
            }});

            // Variables globales para visualización
            let marcadorIncidente, rutaRapidaLayer, rutaSeguraLayer, grafoLayer;
            let mostrarGrafo = MOSTRAR_GRAFO;

            // --- Visualización automática del grafo según el toggle de Streamlit ---
            if (MOSTRAR_GRAFO) {{
                setTimeout(() => {{
                    mostrarGrafoCompleto();
                }}, 500); // Pequeño delay para asegurar que el mapa esté cargado
            }}

            // --- Visualización del Grafo de Red (Completa) ---
            function mostrarGrafoCompleto() {{
                // Crear grupo de capas para el grafo
                grafoLayer = L.layerGroup();
                
                console.log(`🗺️ Visualizando grafo completo: ${{edges.length}} aristas disponibles`);
                
                // Crear set para evitar aristas duplicadas en visualización
                const aristasVisualizadas = new Set();
                let aristasVisibles = 0;
                
                // Mostrar TODAS las aristas del grafo sin límite
                edges.forEach(edge => {{
                    const sourceNode = nodes[edge.source];
                    const targetNode = nodes[edge.target];
                    
                    if (sourceNode && targetNode) {{
                        // Crear ID único para la arista (bidireccional)
                        const aristaId = `${{Math.min(edge.source, edge.target)}}-${{Math.max(edge.source, edge.target)}}`;
                        
                        // Solo agregar si no ha sido visualizada
                        if (!aristasVisualizadas.has(aristaId)) {{
                            aristasVisualizadas.add(aristaId);
                            
                            // Color y grosor según tipo de vía
                            let color, weight, opacity;
                            
                            switch(edge.tipo_via) {{
                                case 'avenida_principal':
                                    color = '#FF6B35'; // Naranja para avenidas
                                    weight = 4;
                                    opacity = 0.8;
                                    break;
                                case 'calle_colectora':
                                    color = '#7209B7'; // Morado para colectoras
                                    weight = 3;
                                    opacity = 0.7;
                                    break;
                                case 'calle_residencial':
                                    color = '#2ECC71'; // Verde para residenciales
                                    weight = 2;
                                    opacity = 0.6;
                                    break;
                                case 'jiron_comercial':
                                    color = '#3498DB'; // Azul para jirones
                                    weight = 2;
                                    opacity = 0.6;
                                    break;
                                default:
                                    color = '#95A5A6'; // Gris para otros
                                    weight = 1;
                                    opacity = 0.5;
                            }}
                            
                            // Crear la línea del grafo
                            L.polyline([
                                [sourceNode.lat, sourceNode.lon],
                                [targetNode.lat, targetNode.lon]
                            ], {{
                                color: color,
                                weight: weight,
                                opacity: opacity,
                                interactive: true
                            }}).bindPopup(`
                                <b>🛣️ Conexión Vial</b><br>
                                <b>Nodos:</b> ${{edge.source}} ↔ ${{edge.target}}<br>
                                <b>Tipo:</b> ${{edge.tipo_via}}<br>
                                <b>Longitud:</b> ${{edge.length.toFixed(1)}}m<br>
                                <b>Velocidad base:</b> ${{edge.velocidad_base}} km/h<br>
                                <b>Factor calidad:</b> ${{edge.factor_calidad}}<br>
                                <small><i>Conexión bidireccional</i></small>
                            `).addTo(grafoLayer);
                            
                            aristasVisibles++;
                        }}
                    }}
                }});
                
                // Agregar algunos nodos importantes como puntos de referencia
                let nodosImportantes = 0;
                Object.keys(nodes).forEach(nodeId => {{
                    const node = nodes[nodeId];
                    if (node && nodosImportantes < 100) {{ // Aumentar límite de nodos importantes
                        // Calcular conectividad del nodo
                        const conexionesEntrada = edges.filter(e => e.target == nodeId).length;
                        const conexionesSalida = edges.filter(e => e.source == nodeId).length;
                        const totalConexiones = conexionesEntrada + conexionesSalida;
                        
                        // Mostrar solo nodos con muchas conexiones (intersecciones importantes)
                        if (totalConexiones >= 4) {{
                            let color, radius;
                            if (totalConexiones >= 10) {{
                                color = '#E74C3C'; radius = 8; // Rojo para super hubs
                            }} else if (totalConexiones >= 6) {{
                                color = '#F39C12'; radius = 6; // Naranja para hubs importantes
                            }} else {{
                                color = '#3498DB'; radius = 4; // Azul para intersecciones normales
                            }}
                            
                            L.circleMarker([node.lat, node.lon], {{
                                radius: radius,
                                fillColor: color,
                                color: '#ffffff',
                                weight: 2,
                                opacity: 1,
                                fillOpacity: 0.8
                            }}).bindPopup(`
                                <b>🏛️ Intersección Importante</b><br>
                                <b>Nodo:</b> ${{nodeId}}<br>
                                <b>Conexiones:</b> ${{totalConexiones}}<br>
                                <b>Entrada:</b> ${{conexionesEntrada}}<br>
                                <b>Salida:</b> ${{conexionesSalida}}<br>
                                <b>Coordenadas:</b> [${{node.lat.toFixed(4)}}, ${{node.lon.toFixed(4)}}]
                            `).addTo(grafoLayer);
                            
                            nodosImportantes++;
                        }}
                    }}
                }});
                
                // Agregar al mapa
                grafoLayer.addTo(map);
                
                console.log(`✅ Grafo completo visualizado: ${{aristasVisibles}} aristas únicas, ${{nodosImportantes}} intersecciones importantes`);
            }}

            function ocultarGrafoCompleto() {{
                if (grafoLayer) {{
                    map.removeLayer(grafoLayer);
                    grafoLayer = null;
                }}
            }}

            // --- Construcción de Lista de Adyacencia con Modelo de Costo Mejorado ---
            
            // --- Factores de Tráfico Granulares (5 Niveles) ---
            const FACTORES_TRAFICO = {{
                "trafico_minimo": {{
                    "avenida_principal": 0.7,
                    "jiron_comercial": 0.8,
                    "calle_colectora": 0.9,
                    "calle_residencial": 1.0
                }},
                "trafico_bajo": {{
                    "avenida_principal": 1.0,
                    "jiron_comercial": 1.1,
                    "calle_colectora": 1.0,
                    "calle_residencial": 1.0
                }},
                "trafico_medio": {{
                    "avenida_principal": 1.5,
                    "jiron_comercial": 1.3,
                    "calle_colectora": 1.2,
                    "calle_residencial": 1.1
                }},
                "trafico_alto": {{
                    "avenida_principal": 2.2,
                    "jiron_comercial": 1.8,
                    "calle_colectora": 1.5,
                    "calle_residencial": 1.2
                }},
                "trafico_extremo": {{
                    "avenida_principal": 3.0,
                    "jiron_comercial": 2.5,
                    "calle_colectora": 2.0,
                    "calle_residencial": 1.3
                }}
            }};
            
            // --- Factores de Zonas Especiales ---
            const FACTORES_ZONA_ESPECIAL = {{
                "mercado": {{ min: 1.70, max: 2.50 }},
                "paradero": {{ min: 1.40, max: 1.60 }},
                "centro_historico": {{ min: 1.30, max: 1.50 }},
                "zona_escolar": {{ min: 2.00, max: 3.50 }},
                "via_mala": {{ min: 1.80, max: 3.00 }},
                "hospital": {{ min: 1.25, max: 1.40 }},
                "cruce_sin_semaforo": {{ min: 1.30, max: 1.70 }}
            }};

            const listaAdyacencia = {{}};
            Object.keys(nodes).forEach(nodeId => {{
                listaAdyacencia[nodeId] = [];
            }});

            edges.forEach(edge => {{
                // 1. Factor de Tráfico según nivel y tipo de vía
                let factorTrafico = 1.0;
                const factoresNivel = FACTORES_TRAFICO[NIVEL_TRAFICO];
                if (factoresNivel && factoresNivel[edge.tipo_via]) {{
                    factorTrafico = factoresNivel[edge.tipo_via];
                }} else {{
                    // Fallback para tipos de vía no definidos
                    switch(edge.tipo_via) {{
                        case "avenida_principal": factorTrafico = 1.5; break;
                        case "jiron_comercial": factorTrafico = 1.3; break;
                        case "calle_colectora": factorTrafico = 1.2; break;
                        case "calle_residencial": factorTrafico = 1.0; break;
                        default: factorTrafico = 1.2;
                    }}
                }}
                
                // 2. Factor Climático
                let factorClima = 1.0;
                switch(CONDICION_CLIMA) {{
                    case "lluvia": factorClima = 1.5; break;  // +50% tiempo
                    case "neblina": factorClima = 1.4; break; // +40% tiempo
                    case "despejado": factorClima = 1.0; break;
                    default: factorClima = 1.0;
                }}
                
                // 3. Factor de Zona Especial (simulado)
                let factorZonaEspecial = 1.0;
                const random = Math.random();
                if (edge.tipo_via === "jiron_comercial" && random < 0.3) {{
                    // 30% probabilidad de ser zona comercial
                    const mercado = FACTORES_ZONA_ESPECIAL.mercado;
                    factorZonaEspecial = mercado.min + (mercado.max - mercado.min) * Math.random();
                }} else if (edge.tipo_via === "avenida_principal" && random < 0.2) {{
                    // 20% probabilidad de paradero informal
                    const paradero = FACTORES_ZONA_ESPECIAL.paradero;
                    factorZonaEspecial = paradero.min + (paradero.max - paradero.min) * Math.random();
                }}
                
                // 4. Tiempo base
                const tiempoBase = edge.length / (edge.velocidad_base * 1000 / 3600);
                
                // 5. Costo para RUTA RÁPIDA (incluye todos los factores)
                const muDinamico = tiempoBase * edge.factor_calidad * factorTrafico * factorClima * factorZonaEspecial;
                
                // 6. Cálculo de σ (sigma) - Incertidumbre según tipo de vía y factores
                let sigmaBase = 0;
                switch(edge.tipo_via) {{
                    case "avenida_principal": sigmaBase = 0.4; break; // Alta incertidumbre
                    case "jiron_comercial": sigmaBase = 0.35; break;  // Alta incertidumbre comercial
                    case "calle_colectora": sigmaBase = 0.25; break;  // Incertidumbre media
                    case "calle_residencial": sigmaBase = 0.15; break; // Baja incertidumbre
                    default: sigmaBase = 0.3; break;
                }}
                
                // Aplicar factores de incertidumbre adicionales
                let factorIncertidumbre = 1.0;
                if (CONDICION_CLIMA === "lluvia") {{
                    factorIncertidumbre *= 1.8; // Mucha más incertidumbre en lluvia
                }} else if (CONDICION_CLIMA === "neblina") {{
                    factorIncertidumbre *= 1.6; // Alta incertidumbre en neblina
                }}
                
                // Incertidumbre por tráfico
                switch(NIVEL_TRAFICO) {{
                    case "trafico_extremo": factorIncertidumbre *= 2.0; break;
                    case "trafico_alto": factorIncertidumbre *= 1.5; break;
                    case "trafico_medio": factorIncertidumbre *= 1.2; break;
                    case "trafico_bajo": factorIncertidumbre *= 0.9; break;
                    case "trafico_minimo": factorIncertidumbre *= 0.7; break;
                }}
                
                // Incertidumbre por zonas especiales
                if (factorZonaEspecial > 1.0) {{
                    factorIncertidumbre *= (1.0 + (factorZonaEspecial - 1.0) * 0.8); // 80% de la penalización se convierte en incertidumbre
                }}
                
                const sigmaDinamico = sigmaBase * muDinamico * factorIncertidumbre;
                
                // 7. Costos finales usando el modelo probabilístico correcto
                const costoRapido = muDinamico; // Ruta rápida: solo tiempo esperado μ(e)
                const costoSeguro = muDinamico + (FACTOR_RIESGO_K * sigmaDinamico); // Ruta segura: μ(e) + k×σ(e)

                // Agregar conexiones bidireccionales
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

            console.log(`✅ Grafo con modelo mejorado construido: ${{Object.keys(listaAdyacencia).length}} nodos`);
            console.log(`📊 Factores aplicados - Tráfico: ${{NIVEL_TRAFICO}}, Clima: ${{CONDICION_CLIMA}}`);

            // --- Función para Recalcular Tiempo Real de una Ruta ---
            function calcularTiempoRealRuta(rutaPath, tipoCosto) {{
                if (!rutaPath || rutaPath.length < 2) return 0;
                
                let tiempoTotal = 0;
                let distanciaTotal = 0;
                let detallesAristas = [];
                
                // Recorrer cada segmento de la ruta
                for (let i = 0; i < rutaPath.length - 1; i++) {{
                    const nodoOrigen = rutaPath[i];
                    const nodoDestino = rutaPath[i + 1];
                    
                    // Buscar la arista entre estos nodos
                    const aristasOrigen = listaAdyacencia[nodoOrigen] || [];
                    const arista = aristasOrigen.find(a => a.node === nodoDestino);
                    
                    if (arista) {{
                        const costoArista = arista[tipoCosto];
                        tiempoTotal += costoArista;
                        distanciaTotal += arista.length;
                        
                        detallesAristas.push({{
                            desde: nodoOrigen,
                            hasta: nodoDestino,
                            tipo_via: arista.tipo_via,
                            longitud: arista.length,
                            tiempo: costoArista
                        }});
                    }}
                }}
                
                return {{
                    tiempoTotal: tiempoTotal,
                    distanciaTotal: distanciaTotal,
                    velocidadPromedio: distanciaTotal > 0 ? (distanciaTotal / tiempoTotal) * 3.6 : 0, // km/h
                    detallesAristas: detallesAristas,
                    numSegmentos: detallesAristas.length
                }};
            }}

            // --- Función para Analizar Composición de Ruta ---
            function analizarComposicionRuta(rutaPath) {{
                if (!rutaPath || rutaPath.length < 2) return {{}};
                
                const composicion = {{
                    avenida_principal: {{ count: 0, distancia: 0 }},
                    calle_colectora: {{ count: 0, distancia: 0 }},
                    calle_residencial: {{ count: 0, distancia: 0 }},
                    jiron_comercial: {{ count: 0, distancia: 0 }},
                    otros: {{ count: 0, distancia: 0 }}
                }};
                
                for (let i = 0; i < rutaPath.length - 1; i++) {{
                    const nodoOrigen = rutaPath[i];
                    const nodoDestino = rutaPath[i + 1];
                    
                    const aristasOrigen = listaAdyacencia[nodoOrigen] || [];
                    const arista = aristasOrigen.find(a => a.node === nodoDestino);
                    
                    if (arista) {{
                        const tipo = arista.tipo_via || 'otros';
                        if (composicion[tipo]) {{
                            composicion[tipo].count++;
                            composicion[tipo].distancia += arista.length;
                        }} else {{
                            composicion.otros.count++;
                            composicion.otros.distancia += arista.length;
                        }}
                    }}
                }}
                
                return composicion;
            }}

            // --- Algoritmo A* ---
            function aStar(inicio, destino, tipoCosto) {{
                const tiempoInicio = performance.now();
                console.log(`🔍 A* iniciado: ${{inicio}} → ${{destino}} [${{tipoCosto}}]`);
                
                if (!nodes[inicio] || !nodes[destino]) {{
                    console.error(`❌ Nodos inválidos`);
                    return null;
                }}
                
                if (inicio === destino) {{
                    return {{ path: [inicio], cost: 0, nodesExplored: 1 }};
                }}
                
                // Heurística admisible
                function heuristica(nodoA, nodoB) {{
                    const pA = nodes[nodoA];
                    const pB = nodes[nodoB];
                    if (!pA || !pB) return Infinity;
                    
                    const lat1 = pA.lat * Math.PI / 180;
                    const lat2 = pB.lat * Math.PI / 180;
                    const deltaLat = lat2 - lat1;
                    const deltaLon = (pB.lon - pA.lon) * Math.PI / 180;
                    
                    const a = Math.sin(deltaLat/2) * Math.sin(deltaLat/2) +
                            Math.cos(lat1) * Math.cos(lat2) *
                            Math.sin(deltaLon/2) * Math.sin(deltaLon/2);
                    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
                    const distancia = 6371000 * c;
                    
                    const velocidadMaxMs = 20;
                    return distancia / velocidadMaxMs;
                }}
                
                const openSet = new Set([inicio]);
                const closedSet = new Set();
                const cameFrom = new Map();
                const gScore = new Map([[inicio, 0]]);
                const fScore = new Map([[inicio, heuristica(inicio, destino)]]);
                
                let nodosExplorados = 0;
                const maxIteraciones = 5000;
                const maxTiempo = 6000;
                
                while (openSet.size > 0 && nodosExplorados < maxIteraciones) {{
                    if (performance.now() - tiempoInicio > maxTiempo) {{
                        console.warn(`⏰ Timeout alcanzado`);
                        break;
                    }}
                    
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
                        const tiempoTotal = performance.now() - tiempoInicio;
                        console.log(`✅ Ruta encontrada en ${{tiempoTotal.toFixed(0)}}ms: ${{ruta.length}} nodos`);
                        return {{ 
                            path: ruta, 
                            cost: gScore.get(destino), 
                            nodesExplored: nodosExplorados,
                            timeMs: tiempoTotal
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

            // --- Manejo de Eventos de Emergencia ---
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
                        <p style="font-size: 0.8em; color: #666;">⏰ <span id="processing-time">${{HORA_ACTUAL}}</span></p>
                        <style>
                            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
                        </style>
                    </div>`;
                
                // Asegurar que el panel esté visible durante el procesamiento
                if (panelMinimized) {{
                    togglePanel();
                }}
                
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
            
            // --- Función de Procesamiento de Emergencia ---
            function procesarEmergencia(coordsIncidente) {{
                try {{
                    // Encontrar nodo más cercano
                    let nodoDestino = null;
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
            
            // --- Función para Calcular Rutas Duales ---
            function calcularRutasDuales(mejorPatrulla, nodoDestino) {{
                try {{
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="text-align: center; padding: 15px;">
                            <h5>🎯 Calculando rutas para ${{mejorPatrulla.id}}</h5>
                            <p>Generando recomendaciones...</p>
                        </div>`;
                    
                    // Calcular ambas rutas
                    const rutaRapida = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_rapido');
                    const rutaSegura = aStar(mejorPatrulla.nodo_actual, nodoDestino, 'costo_seguro');
                    
                    if (!rutaRapida) {{
                        document.getElementById('contenido-recomendaciones').innerHTML = 
                            "<div style='color: #dc3545; font-weight: bold; padding: 15px;'>❌ Error: No se pudo calcular la ruta</div>";
                        return;
                    }}
                    
                    // Recalcular tiempos reales usando los atributos de las aristas
                    const tiempoRealRapida = calcularTiempoRealRuta(rutaRapida.path, 'costo_rapido');
                    const tiempoRealSegura = rutaSegura ? calcularTiempoRealRuta(rutaSegura.path, 'costo_seguro') : null;
                    
                    // Analizar composición de rutas
                    const composicionRapida = analizarComposicionRuta(rutaRapida.path);
                    const composicionSegura = rutaSegura ? analizarComposicionRuta(rutaSegura.path) : null;
                    
                    function formatearTiempo(segundos) {{
                        if (!isFinite(segundos)) return "∞";
                        const mins = Math.floor(segundos / 60);
                        const segs = Math.round(segundos % 60);
                        return `${{mins}}:${{segs.toString().padStart(2, '0')}}`;
                    }}
                    
                    function formatearDistancia(metros) {{
                        if (metros >= 1000) {{
                            return `${{(metros / 1000).toFixed(1)}} km`;
                        }}
                        return `${{metros.toFixed(0)}} m`;
                    }}
                    
                    function generarComposicionHTML(composicion) {{
                        let html = '<div style="font-size: 0.8em; margin-top: 8px;">';
                        html += '<b>Composición de vías:</b><br>';
                        
                        Object.keys(composicion).forEach(tipo => {{
                            const data = composicion[tipo];
                            if (data.count > 0) {{
                                const emoji = {{
                                    'avenida_principal': '🟠',
                                    'calle_colectora': '🟣', 
                                    'calle_residencial': '🟢',
                                    'jiron_comercial': '🔵',
                                    'otros': '⚫'
                                }}[tipo] || '⚪';
                                
                                const nombre = {{
                                    'avenida_principal': 'Avenidas',
                                    'calle_colectora': 'Colectoras',
                                    'calle_residencial': 'Residenciales', 
                                    'jiron_comercial': 'Jirones',
                                    'otros': 'Otros'
                                }}[tipo] || tipo;
                                
                                html += `${{emoji}} ${{nombre}}: ${{data.count}} (${{formatearDistancia(data.distancia)}})<br>`;
                            }}
                        }});
                        
                        html += '</div>';
                        return html;
                    }}
                    
                    let htmlRecomendaciones = `<h5>🎯 Análisis Detallado para ${{mejorPatrulla.id}}</h5>`;
                    
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
                            ⏱️ <b>Tiempo estimado:</b> ${{formatearTiempo(tiempoRealRapida.tiempoTotal)}}<br>
                            📏 <b>Distancia:</b> ${{formatearDistancia(tiempoRealRapida.distanciaTotal)}}<br>
                            � <b>Velocidad promedio:</b> ${{tiempoRealRapida.velocidadPromedio.toFixed(1)}} km/h<br>
                            📍 <b>Segmentos:</b> ${{tiempoRealRapida.numSegmentos}} tramos<br>
                            🔍 <b>Nodos explorados:</b> ${{rutaRapida.nodesExplored}}<br>
                            🧮 <b>Función:</b> μ(e)
                            ${{generarComposicionHTML(composicionRapida)}}
                        </div>`;
                    }}
                    
                    // Visualizar ruta segura
                    if (rutaSegura && rutaSegura.path && tiempoRealSegura) {{
                        const coordsRuta = rutaSegura.path.map(n => [nodes[n].lat, nodes[n].lon]);
                        rutaSeguraLayer = L.polyline(coordsRuta, {{ 
                            color: '#3498db', 
                            weight: 6, 
                            opacity: 0.9,
                            dashArray: '15, 8'
                        }}).addTo(map);
                        
                        const diferenciaTiempo = tiempoRealSegura.tiempoTotal - tiempoRealRapida.tiempoTotal;
                        const diferenciaPorcentaje = ((diferenciaTiempo / tiempoRealRapida.tiempoTotal) * 100).toFixed(1);
                        const diferenciaDist = tiempoRealSegura.distanciaTotal - tiempoRealRapida.distanciaTotal;
                        
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #3498db; padding: 12px; margin: 8px 0; background: #f0f8ff; border-radius: 5px;">
                            <b>2. 🛡️ Ruta Segura</b><br>
                            ⏱️ <b>Tiempo estimado:</b> ${{formatearTiempo(tiempoRealSegura.tiempoTotal)}}<br>
                            📏 <b>Distancia:</b> ${{formatearDistancia(tiempoRealSegura.distanciaTotal)}}<br>
                            � <b>Velocidad promedio:</b> ${{tiempoRealSegura.velocidadPromedio.toFixed(1)}} km/h<br>
                            📍 <b>Segmentos:</b> ${{tiempoRealSegura.numSegmentos}} tramos<br>
                            🔍 <b>Nodos explorados:</b> ${{rutaSegura.nodesExplored}}<br>
                            📊 <b>Diferencia tiempo:</b> +${{formatearTiempo(diferenciaTiempo)}} (+${{diferenciaPorcentaje}}%)<br>
                            📊 <b>Diferencia distancia:</b> ${{diferenciaDist >= 0 ? '+' : ''}}${{formatearDistancia(Math.abs(diferenciaDist))}}<br>
                            🧮 <b>Función:</b> μ(e) + k×σ(e) [k=${{FACTOR_RIESGO_K}}]
                            ${{generarComposicionHTML(composicionSegura)}}
                        </div>`;
                        
                        // Comparación de rutas
                        const rutasSonDiferentes = JSON.stringify(rutaRapida.path) !== JSON.stringify(rutaSegura.path);
                        const recomendacion = rutasSonDiferentes ? 
                            (diferenciaTiempo / tiempoRealRapida.tiempoTotal < 0.5 ? 
                                "🛡️ Se recomienda la ruta segura (buena relación tiempo/seguridad)" : 
                                "⚡ Se recomienda la ruta rápida (diferencia de tiempo significativa)") :
                            "⚠️ Ambas rutas son idénticas - revisar factores de seguridad";
                        
                        htmlRecomendaciones += `
                        <div style="background: #f8f9fa; padding: 12px; border-radius: 5px; margin: 10px 0;">
                            <h6>🤖 Análisis de Recomendación:</h6>
                            <p style="font-size: 0.9em; margin: 5px 0;">
                                <b>Estado de rutas:</b> ${{rutasSonDiferentes ? '✅ Rutas diferentes encontradas' : '⚠️ Rutas idénticas'}}
                            </p>
                            <p style="font-size: 0.9em; margin: 5px 0;">
                                <b>Recomendación:</b> ${{recomendacion}}
                            </p>
                        </div>`;
                    }} else {{
                        htmlRecomendaciones += `
                        <div style="border-left: 5px solid #ffc107; padding: 12px; margin: 8px 0; background: #fff9e6; border-radius: 5px;">
                            <b>⚠️ Ruta Segura</b><br>
                            No se pudo calcular una ruta segura alternativa.
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

            // --- Función de Asignación de Patrulla ---
            window.asignarPatrulla = function(idPatrulla, tipoRuta) {{
                console.log(`Asignando ${{idPatrulla}} con ruta ${{tipoRuta}}`);
                
                const patrulla = patrullas.find(p => p.id === idPatrulla);
                if (patrulla) {{
                    patrulla.status = 'en_ruta';
                    patrulla.marker.setIcon(L.divIcon({{ 
                        html: `<div class="patrol-ocupado">${{patrulla.id}}</div>`, 
                        iconSize: [32, 32], 
                        className: '' 
                    }}));
                    
                    const tipoTexto = tipoRuta === 'rapida' ? 'Rápida ⚡' : 'Segura 🛡️';
                    const mensaje = `✅ ${{patrulla.id}} despachada<br>📍 Ruta: ${{tipoTexto}}<br>🚀 Estado: En camino`;
                    
                    document.getElementById('contenido-recomendaciones').innerHTML = `
                        <div style="color: #28a745; font-weight: bold; padding: 20px; background: #d4edda; border-radius: 8px; border: 2px solid #c3e6cb; text-align: center;">
                            ${{mensaje}}
                        </div>`;
                }}
            }}

            // --- Hacer función global ---
            window.asignarPatrulla = asignarPatrulla;
        </script>
    </body>
    </html>
    """
    components.html(mapa_html, height=750)

    # Estado actual del sistema
    st.markdown("### 🔄 Estado Actual")
    estado_df = pd.DataFrame(patrullas_data)
    st.dataframe(estado_df, hide_index=True)

else:
    st.error("❌ No se pudo cargar el grafo de Tacna. Verifique la conexión a internet y reinicie la aplicación.")
    st.info("💡 **Sugerencia:** Asegúrese de tener una conexión estable a internet para descargar los datos de OpenStreetMap.")
